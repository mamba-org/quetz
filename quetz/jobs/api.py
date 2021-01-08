# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import pickle
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field, validator

from quetz import authorization
from quetz.dao import Dao
from quetz.deps import get_dao, get_db, get_rules
from quetz.jobs import models as job_db_models
from quetz.rest_models import User

from .models import JobStatus, TaskStatus

api_router = APIRouter()


class JobBase(BaseModel):

    items_spec: str = Field(None, title='Item selector spec')
    manifest: str = Field(None, title='Name of the function')


class Job(JobBase):
    id: int = Field(None, title='Unique id for job')
    owner: User = Field(None, title='User profile of the owner')

    created: datetime = Field(None, title='Created at')

    status: JobStatus = Field(None, title='Status of the job (running, paused, ...)')

    @validator("manifest", pre=True)
    def convert_name(cls, v):
        return pickle.loads(v).__name__

    class Config:
        orm_mode = True


class Task(BaseModel):
    id: int = Field(None, title='Unique id for task')
    job_id: int = Field(None, title='ID of the parent job')
    package_version: dict = Field(None, title='Package version')
    created: datetime = Field(None, title='Created at')
    status: TaskStatus = Field(None, title='Status of the task (running, paused, ...)')

    @validator("package_version", pre=True)
    def convert_package_version(cls, v):
        return {'filename': v.filename, 'id': uuid.UUID(bytes=v.id).hex}

    class Config:
        orm_mode = True


@api_router.get("/api/jobs", tags=["Jobs"], response_model=List[Job])
def get_jobs(
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    auth.assert_jobs()
    return dao.get_jobs()


@api_router.post("/api/jobs", tags=["Jobs"], status_code=201)
def post_jobs(
    job: JobBase,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    """create a new job"""
    user = auth.assert_user()
    auth.assert_jobs()
    dao.create_job(user, job.manifest, job.items_spec)


def get_job_or_fail(
    job_id: int,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
) -> job_db_models.Job:

    auth.assert_jobs()

    job = dao.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Job with id {job_id} not found",
        )

    return job


@api_router.get("/api/jobs/{job_id}", tags=["Jobs"], response_model=List[Task])
def get_tasks(
    dao: Dao = Depends(get_dao),
    job: job_db_models.Job = Depends(get_job_or_fail),
    auth: authorization.Rules = Depends(get_rules),
):
    auth.assert_jobs()
    return job.tasks


@api_router.put("/api/jobs/{job_id}", tags=["Jobs"])
def put_job(
    db=Depends(get_db),
    job: job_db_models.Job = Depends(get_job_or_fail),
    auth: authorization.Rules = Depends(get_rules),
):
    """refresh job (re-run on new packages)"""
    auth.assert_jobs()
    job.status = JobStatus.pending  # type: ignore
    db.commit()


def get_router():
    return api_router
