# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import logging
import re
import time
from typing import Dict, List

import sqlalchemy as sa

from quetz.db_models import PackageVersion
from quetz.jobs.models import ItemsSelection, Job, JobStatus, Task, TaskStatus
from quetz.tasks.common import ACTION_HANDLERS

logger = logging.getLogger('quetz.tasks')
# manager = RQManager("127.0.0.1", 6379, 0, "", {}, config)


def build_queue(job):
    job.status = JobStatus.queued


def parse_conda_spec(conda_spec: str):
    pattern = r'(\w[^ =<>!~]+)([><!=~,\.0-9]+[0-9])?'
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
        pass

    def run_jobs(self, job_id=None, force=False):
        db = self.db
        jobs = db.query(Job).filter(Job.status == JobStatus.pending)
        if job_id:
            jobs = jobs.filter(Job.id == job_id)
        for job in jobs:
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

            if job.items_spec:
                try:
                    filter_expr = build_sql_from_package_spec(job.items_spec)
                except Exception as e:
                    logger.error(f"got error when parsing package spec: {e}")
                    job.status = JobStatus.failed
                    continue
                q = q.filter(filter_expr)
            else:
                # it might be also job created in actions
                # so skipping here
                continue

            job.status = JobStatus.running

            task = None
            for version in q:
                task = Task(job=job, package_version=version)
                db.add(task)
            if not task:
                logger.warning(
                    f"no versions matching the package spec {job.items_spec}. skipping."
                )
                if job.items_spec:
                    # actions have no related package versions
                    job.status = JobStatus.success
        db.commit()

    def add_task_to_queue(self, db, manager, task, *args, func=None, **kwargs):
        """add task to the queue"""

        db = self.db
        manager = self.manager
        _process_cache = self._process_cache

        if func is None:
            func = task.job.manifest
        task.status = TaskStatus.pending
        task.job.status = JobStatus.running
        db.add(task)
        db.commit()
        job = manager.execute(func, *args, task_id=task.id, **kwargs)
        _process_cache[task.id] = job
        return job

    def run_tasks(self):
        """dispatch tasks"""

        db = self.db
        manager = self.manager

        tasks = db.query(Task).filter(Task.status == TaskStatus.created)
        task: Task
        logger.info(f"Got pending tasks: {tasks.count()}")
        jobs = []
        for task in tasks:
            if not task.package_version:
                action_name = task.job.manifest.decode('ascii')
                try:
                    action_func = ACTION_HANDLERS[action_name]
                except KeyError:
                    logger.error(f"action {action_name} not known")
                    continue
                kwargs = {"func": action_func}
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
            job = self.add_task_to_queue(db, manager, task, **kwargs)
            jobs.append(job)
        db.commit()
        return jobs

    def check_status(self):

        tasks = (
            self.db.query(Task)
            .filter(Task.status.in_([TaskStatus.running, TaskStatus.pending]))
            .filter(Task.package_version_id.isnot(None))
        )
        for task in tasks:
            if task.id not in self._process_cache:
                logger.warning(f"running process for task {task} is lost, restarting")
                task.status = TaskStatus.created
        self.db.commit()

    def run(self):
        """main loop"""

        while True:
            self.run_jobs()
            self.run_tasks()
            self.check_status()
            time.sleep(5)
