from typing import Optional

import quetz.database
from quetz.config import Config
from quetz.db_models import PackageVersion
from quetz.jobs.models import ItemsSelection, Job, JobStatus, Task, TaskStatus
from quetz.tasks.workers import SubprocessWorker

# manager = RQManager("127.0.0.1", 6379, 0, "", {}, config)


_job_cache = {}


def build_queue(job):
    job.status = JobStatus.queued


def run_jobs(db):
    for job in db.query(Job).filter(Job.status == JobStatus.pending):
        job.status = JobStatus.running
        if job.items == ItemsSelection.all:
            for version in db.query(PackageVersion):
                task = Task(job=job, package_version=version)
                db.add(task)
    db.commit()


def function(manifest: str = "", package_version: Optional[dict] = None):
    import pickle

    func = pickle.loads(manifest)
    func(package_version)


def run_tasks(db, manager):

    tasks = db.query(Task).filter(Task.status == TaskStatus.pending)
    task: Task
    jobs = []
    for task in tasks:
        version_dict = {"filename": task.package_version.filename}
        job = manager.execute(
            function, manifest=task.job.manifest, package_version=version_dict
        )
        _job_cache[task.id] = job
        jobs.append(job)
        task.status = TaskStatus.running
    db.commit()
    return jobs


def check_status(db):
    tasks = db.query(Task).filter(Task.status == TaskStatus.running)
    try:
        for task in tasks:
            job = _job_cache[task.id]
            if job.done:
                task.status = TaskStatus.success
                _job_cache.pop(task.id)
    finally:
        db.commit()


if __name__ == "__main__":
    import time

    config = Config()
    db = quetz.database.get_session(config.sqlalchemy_database_url)
    manager = SubprocessWorker("", {}, config)
    while True:
        run_jobs(db)
        run_tasks(db, manager)
        check_status(db)
        time.sleep(5)
