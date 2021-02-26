import json

from quetz.jobs.models import Job, Task


class JobsDao:
    def __init__(self, db):
        self.db = db

    def create_task(self, job_manifest, user_id, extra_args={}):
        if extra_args:
            extra_args_json = json.dumps(extra_args)
        else:
            extra_args_json = None
        job = Job(manifest=job_manifest, owner_id=user_id, extra_args=extra_args_json)
        task = Task(job=job)
        self.db.add(job)
        self.db.add(task)
        self.db.commit()
        return task
