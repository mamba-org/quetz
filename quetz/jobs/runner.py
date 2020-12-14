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

        (
            db.query(Job)
            .filter(Job.status == JobStatus.running)
            .filter(~Job.tasks.any(Task.status == TaskStatus.running))
            .update({"status": JobStatus.success}, synchronize_session=False)
        )
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
