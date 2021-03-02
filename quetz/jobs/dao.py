import json
from datetime import datetime
from typing import Optional

from quetz.jobs.models import Job, JobStatus


class JobsDao:
    def __init__(self, db):
        self.db = db

    def create_job(
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
            status=JobStatus.pending,
            start_at=start_at,
            repeat_every_seconds=repeat_every_seconds,
        )
        self.db.add(job)
        self.db.commit()
        return job
