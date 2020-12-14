import re
from typing import Dict, List

import sqlalchemy as sa

from quetz.db_models import PackageVersion
from quetz.jobs.models import ItemsSelection, Job, JobStatus, Task, TaskStatus

# manager = RQManager("127.0.0.1", 6379, 0, "", {}, config)


_job_cache = {}


def build_queue(job):
    job.status = JobStatus.queued


def parse_conda_spec(conda_spec: str):
    exprs_list = conda_spec.split(',')

    package_specs = []
    for package_spec in exprs_list:
        # https://github.com/conda/conda/blob/aed799b56d9ee16a3653928527e2af6e41394e85/conda/models/match_spec.py#L681
        m3 = re.match(r'([^ =<>!~]+)?([><!=~ ].+)?', package_spec)
        if m3:
            name, spec_str = m3.groups()
        else:
            raise ValueError("can not parse package version spec")

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
        else:
            raise NotImplementedError("version operator not implemented")

        package_specs.append({"version": condition, "package_name": ("eq", name)})
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
                filter_expr = build_sql_from_package_spec(job.items_spec)
                q = q.filter(filter_expr)
            for version in q:
                task = Task(job=job, package_version=version)
                db.add(task)
    db.commit()


def run_tasks(db, manager):

    tasks = db.query(Task).filter(Task.status == TaskStatus.pending)
    task: Task
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
