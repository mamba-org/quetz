import json
from datetime import datetime
from typing import Optional

from quetz.jobs.models import Job, JobStatus, Task


class JobsDao:
    def __init__(self, db):
        self.db = db

    def create_task(
        self,
        job_manifest,
        user_id,
        extra_args={},
        start_at: Optional[datetime] = None,
        repeat_every_seconds: Optional[int] = None,
    ):
        extra_args_json: Optional[str]
        if extra_args:
            extra_args_json = json.dumps(extra_args)
        else:
            extra_args_json = None
        job = Job(
            manifest=job_manifest,
            owner_id=user_id,
            extra_args=extra_args_json,
            status=JobStatus.running,
            start_at=start_at,
            repeat_every_seconds=repeat_every_seconds,
        )
        task = Task(job=job)
        self.db.add(job)
        self.db.add(task)
        self.db.commit()
        return task
