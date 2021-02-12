from quetz.jobs.models import Job, Task


class JobsDao:
    def __init__(self, db):
        self.db = db

    def create_task(self, job_manifest, user_id):
        job = Job(manifest=job_manifest, owner_id=user_id)
        task = Task(job=job)
        self.db.add(job)
        self.db.add(task)
        self.db.commit()
        return task
