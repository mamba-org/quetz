# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import logging
import pickle
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List

import sqlalchemy as sa
from sqlalchemy import Boolean
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import FunctionElement

from quetz.db_models import PackageVersion
from quetz.jobs.models import ItemsSelection, Job, JobStatus, Task, TaskStatus
from quetz.jobs.rest_models import parse_job_manifest

logger = logging.getLogger('quetz.tasks')


class any_true(FunctionElement):
    inherit_cache = True
    name = "anytrue"
    type = Boolean()


@compiles(any_true, 'sqlite')
def sqlite_any(element, compiler, **kw):
    return 'max(%s)' % compiler.process(element.clauses, **kw)


@compiles(any_true, 'postgresql')
def pg_any(element, compiler, **kw):
    return 'bool_or(%s)' % compiler.process(element.clauses, **kw)


class all_true(FunctionElement):
    inherit_cache = True
    name = "alltrue"
    type = Boolean()


@compiles(all_true, 'sqlite')
def sqlite_all(element, compiler, **kw):
    return 'min(%s)' % compiler.process(element.clauses, **kw)


@compiles(all_true, 'postgresql')
def pg_all(element, compiler, **kw):
    return 'bool_and(%s)' % compiler.process(element.clauses, **kw)


def build_queue(job):
    job.status = JobStatus.queued


def parse_conda_spec(conda_spec: str):

    pattern = r'([a-zA-Z\*][^ =<>!~]*)([><!=~,\.0-9]+[0-9])?'
    exprs_list = re.findall(pattern, conda_spec)

    package_specs = []
    for name, versions in exprs_list:
        version_spec = None
        for spec_str in versions.split(','):
            if spec_str.startswith("=="):
                condition = ("eq", spec_str[2:])
            elif spec_str.startswith(">="):
                condition = ("gte", spec_str[2:])
            elif spec_str.startswith("<="):
                condition = ("lte", spec_str[2:])
            elif spec_str.startswith(">"):
                condition = ("gt", spec_str[1:])
            elif spec_str.startswith("<"):
                condition = ("lt", spec_str[1:])
            elif not spec_str:
                continue
            else:
                raise NotImplementedError("version operator not implemented")
            if version_spec:
                version_spec = ("and", version_spec, condition)
            else:
                version_spec = condition
        if "*" in name:
            dict_spec = {"package_name": ("like", name)}
        else:
            dict_spec = {"package_name": ("eq", name)}
        if version_spec:
            dict_spec["version"] = version_spec
        package_specs.append(dict_spec)
    return package_specs


def mk_sql_expr(dict_spec: List[Dict]):
    def _make_op(column, expr):
        op = expr[0]
        v = expr[1:]
        if op == 'eq':
            return column == v[0]
        elif op == 'in':
            return column.in_(v[0])
        elif op == 'lt':
            return column < v[0]
        elif op == 'gt':
            return column > v[0]
        elif op == 'gte':
            return column >= v[0]
        elif op == 'lte':
            return column <= v[0]
        elif op == "like":
            return column.ilike(v[0].replace("*", "%"))
        elif op == "and":
            left = _make_op(column, v[0])
            right = _make_op(column, v[1])
            return sa.and_(left, right)
        elif op == "or":
            left = _make_op(column, v[0])
            right = _make_op(column, v[1])
            return sa.or_(left, right)
        else:
            raise NotImplementedError(f"operator '{op}' not known")

    if not dict_spec:
        return False

    or_elements = []
    for el in dict_spec:
        and_elements = []
        for k, expr in el.items():
            column = getattr(PackageVersion, k)
            and_elements.append(_make_op(column, expr))

        expr = sa.and_(*and_elements)
        or_elements.append(expr)
    sql_expr = sa.or_(*or_elements)
    return sql_expr


def build_sql_from_package_spec(selector: str):
    dict_spec = parse_conda_spec(selector)
    sql_expr = mk_sql_expr(dict_spec)
    return sql_expr


class Supervisor:
    """Watches for new jobs and dispatches tasks."""

    def __init__(self, db, manager):
        self.db = db
        self.manager = manager
        self._process_cache = {}
        self._reset_tasks_after_restart()
        pass

    def _select_package_versions(self, job, force=False):
        db = self.db

        if job.items == ItemsSelection.all:
            if force:
                q = db.query(PackageVersion)
            else:
                existing_task = (
                    db.query(Task.package_version_id, Task.id.label("task_id"))
                    .filter(Task.job_id == job.id)
                    .filter(Task.status != TaskStatus.skipped)
                    .subquery()
                )
                q = (
                    db.query(PackageVersion)
                    .outerjoin(
                        existing_task,
                        PackageVersion.id == existing_task.c.package_version_id,
                    )
                    .filter(existing_task.c.task_id.is_(None))
                )
        else:
            raise NotImplementedError(f"selection {job.items} is not implemented")

        filter_expr = build_sql_from_package_spec(job.items_spec)
        q = q.filter(filter_expr)

        return q

    def run_jobs(self, job_id=None, force=False):
        now = datetime.utcnow()
        db = self.db
        jobs = db.query(Job).filter(Job.status == JobStatus.pending)
        if jobs.count():
            logger.info(f"Got pending jobs: {jobs.count()}")
        if job_id:
            jobs = jobs.filter(Job.id == job_id)
        for job in jobs:
            if job.start_at and job.start_at > now:
                continue

            should_repeat = (
                job.repeat_every_seconds
                and (job.updated + timedelta(seconds=job.repeat_every_seconds)) < now
            )

            if job.items_spec is not None:
                # it's a "package-version job"

                try:
                    force = force or should_repeat
                    q = self._select_package_versions(job, force=force)
                except Exception as e:
                    job.status = JobStatus.failed
                    logger.error(f"got error when parsing package spec: {e}")
                    continue

                task = None
                for version in q:
                    task = Task(job=job, package_version=version)
                    db.add(task)

                if not task and not job.repeat_every_seconds:
                    logger.info(
                        f"No new versions matching the package spec {job.items_spec}. "
                        f"Skipping job {job.id}."
                    )
                    job.status = JobStatus.success
                else:
                    job.status = JobStatus.running
                    job.updated = now

            else:
                # it's a "channel action job"
                if not job.tasks or should_repeat:
                    task = Task(job=job)
                    db.add(task)
                    job.updated = now
                    job.status = JobStatus.running

            db.commit()

    def add_task_to_queue(self, db, task, *args, **kwargs):
        """add task to the queue"""

        db = self.db
        manager = self.manager
        _process_cache = self._process_cache

        try:
            action_name = task.job.manifest.decode('ascii')
            action_func = parse_job_manifest(action_name)
        except UnicodeDecodeError:
            try:
                action_func = pickle.loads(task.job.manifest)
            except pickle.UnpicklingError:
                logger.error(
                    f"job {task.job_id} manifest contains non-ascii characters"
                )
                raise
        except ValueError:
            logger.error(f"job action {action_name} not known")
            raise

        task.status = TaskStatus.pending
        task.job.status = JobStatus.running
        db.add(task)
        db.commit()
        job = manager.execute(action_func, *args, task_id=task.id, **kwargs)
        _process_cache[task.id] = job
        return job

    def run_tasks(self):
        """dispatch tasks"""

        db = self.db

        tasks = db.query(Task).filter(Task.status == TaskStatus.created)
        task: Task
        if tasks.count():
            logger.info(f"Got pending tasks: {tasks.count()}")
        jobs = []
        for task in tasks:
            if not task.package_version:
                kwargs = {}
            else:
                kwargs = {
                    'package_version': {
                        "filename": task.package_version.filename,
                        "channel_name": task.package_version.channel_name,
                        "package_format": task.package_version.package_format,
                        "platform": task.package_version.platform,
                        "version": task.package_version.version,
                        "build_string": task.package_version.build_string,
                        "build_number": task.package_version.build_number,
                        "size": task.package_version.size,
                        "package_name": task.package_version.package_name,
                        "info": task.package_version.info,
                        "uploader_id": task.package_version.uploader_id,
                    }
                }
            try:
                job = self.add_task_to_queue(db, task, **kwargs)
                jobs.append(job)
            except Exception:
                logger.exception(f"task {task.id} failed due to error")
                task.status = TaskStatus.failed

        db.commit()
        return jobs

    def _reset_tasks_after_restart(self):

        # tasks lost after restart
        n_updated = (
            self.db.query(Task)
            .filter(Task.status.in_([TaskStatus.running, TaskStatus.pending]))
            .update({Task.status: TaskStatus.failed}, synchronize_session=False)
        )
        self.db.commit()

        if n_updated > 0:
            logger.warning(f"{n_updated} tasks set to failed due to supervisor restart")

    def _update_running_jobs(self):
        """Update status of running/pending jobs."""

        task_done = Task.status.in_([TaskStatus.failed, TaskStatus.success])
        running_job = Job.status.in_([JobStatus.running, JobStatus.pending])
        # we are using func.min/max to implement all/any aggregate functions
        results = (
            self.db.query(
                Task.job_id,
                func.min(Job.repeat_every_seconds),
                # flag if any task failed
                any_true(Task.status == TaskStatus.failed).label("failed"),
            )
            .outerjoin(Job)
            .filter(running_job)
            .group_by(Task.job_id)
            # select jobs where all tasks are finsihed
            .having(all_true(task_done))
            .all()
        )
        for job_id, repeat, failed in results:
            if repeat:
                # job with repeat non-null repeat column should be
                # kept runing until cancelled
                status = JobStatus.pending
            elif failed:
                status = JobStatus.failed
            else:
                status = JobStatus.success
            self.db.query(Job).filter(Job.id == job_id).update({Job.status: status})
        self.db.commit()

    def check_status(self):
        self._update_running_jobs()

    def run_once(self):
        self.run_jobs()
        self.run_tasks()
        self.check_status()

    def run(self):
        """main loop"""

        while True:
            self.run_once()
            time.sleep(5)
