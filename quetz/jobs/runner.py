# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import logging
import re
from typing import Dict, List

import sqlalchemy as sa

from quetz.db_models import PackageVersion
from quetz.jobs.models import ItemsSelection, Job, JobStatus, Task, TaskStatus

logger = logging.getLogger('quetz-cli')
# manager = RQManager("127.0.0.1", 6379, 0, "", {}, config)


_job_cache = {}


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


def run_jobs(db):
    for job in db.query(Job).filter(Job.status == JobStatus.pending):
        job.status = JobStatus.running
        if job.items == ItemsSelection.all:
            q = db.query(PackageVersion)
            if job.items_spec:
                try:
                    filter_expr = build_sql_from_package_spec(job.items_spec)
                except Exception as e:
                    logger.error(f"got error when parsing package spec: {e}")
                    job.status = JobStatus.failed
                    continue
                q = q.filter(filter_expr)
            else:
                logger.warning("empty package spec returns no results")
                q = []
            task = None
            for version in q:
                task = Task(job=job, package_version=version)
                db.add(task)
            if not task:
                logger.warning(
                    f"no versions matching the package spec {job.items_spec}. skipping."
                )
                job.status = JobStatus.success
    db.commit()


def run_tasks(db, manager):

    tasks = db.query(Task).filter(Task.status == TaskStatus.pending)
    task: Task
    logger.info(f"Got pending tasks: {tasks.count()}")
    jobs = []
    for task in tasks:
        version_dict = {
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
        job = manager.execute(task.job.manifest, package_version=version_dict)
        _job_cache[task.id] = job
        jobs.append(job)
        task.status = TaskStatus.running
        task.job.status = JobStatus.running
    db.commit()
    return jobs


def check_status(db):
    tasks = db.query(Task).filter(Task.status == TaskStatus.running)
    try:
        for task in tasks:
            job = _job_cache[task.id]
            if job.done:
                task.status = (
                    TaskStatus.success if job.status == 'success' else TaskStatus.failed
                )
                _job_cache.pop(task.id)

        # update jobs with all tasks finished
        (
            db.query(Job)
            .filter(Job.status == JobStatus.running)
            .filter(~Job.tasks.any(Task.status == TaskStatus.running))
            .update({"status": JobStatus.success}, synchronize_session=False)
        )
    finally:
        db.commit()
