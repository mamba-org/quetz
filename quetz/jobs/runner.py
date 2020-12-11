import quetz.database
from quetz.config import Config
from quetz.db_models import PackageVersion
from quetz.jobs.models import ItemsSelection, Job, JobStatus, Task, TaskStatus
from quetz.tasks.workers import SubprocessWorker

# manager = RQManager("127.0.0.1", 6379, 0, "", {}, config)


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


def function(package_version: dict):
    pass


def run_tasks(db, manager):

    tasks = db.query(Task).filter(Task.status == TaskStatus.pending)
    for task in tasks:
        version_dict = {"filename": task.package_version.filename}
        manager.execute(function, version_dict)


if __name__ == "__main__":
    import time

    config = Config()
    db = quetz.database.get_session(config.sqlalchemy_database_url)
    manager = SubprocessWorker("", {}, config)
    while True:
        run_jobs(db)
        run_tasks(db, manager)
        time.sleep(5)
