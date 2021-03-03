# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from quetz import authorization
from quetz.config import PAGINATION_LIMIT
from quetz.dao import Dao
from quetz.deps import get_dao, get_db, get_rules
from quetz.jobs import models as job_db_models
from quetz.rest_models import PaginatedResponse

from .models import JobStatus, TaskStatus
from .rest_models import Job, JobBase, JobUpdateModel, Task

api_router = APIRouter()

logger = logging.getLogger("quetz")


@api_router.get("/api/jobs", tags=["Jobs"], response_model=PaginatedResponse[Job])
def get_jobs(
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
    status: List[JobStatus] = Query([JobStatus.pending, JobStatus.running]),
    skip: int = 0,
    limit: int = PAGINATION_LIMIT,
):
    # if this is merged https://github.com/tiangolo/fastapi/issues/2077
    # we will be able to use non-exploded list, i.e., ?state=running,pending
    user_id = auth.assert_user()

    if auth.is_user_elevated(user_id):
        return dao.get_jobs(states=status, skip=skip, limit=limit)

    return dao.get_jobs(states=status, skip=skip, limit=limit, owner_id=user_id)


@api_router.post("/api/jobs", tags=["Jobs"], status_code=201, response_model=Job)
def create_job(
    job: JobBase,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    """create a new job"""
    user = auth.assert_user()
    # only admins can create jobs through /jobs API
    auth.assert_jobs(None)
    new_job = dao.create_job(user, job)
    return new_job


def get_job_or_fail(
    job_id: int,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
) -> job_db_models.Job:

    job = dao.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Job with id {job_id} not found",
        )

    auth.assert_jobs(job.owner_id)

    return job


@api_router.get("/api/jobs/{job_id}", tags=["Jobs"], response_model=Job)
def get_job(
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
    job: job_db_models.Job = Depends(get_job_or_fail),
):
    auth.assert_jobs(owner_id=job.owner_id)
    return job


@api_router.patch("/api/jobs/{job_id}", tags=["Jobs"])
def update_job(
    job_data: JobUpdateModel,
    db=Depends(get_db),
    job: job_db_models.Job = Depends(get_job_or_fail),
    auth: authorization.Rules = Depends(get_rules),
):
    """refresh job (re-run on new packages)"""
    auth.assert_jobs(owner_id=job.owner_id)
    job.status = job_data.status  # type: ignore

    if job_data.force and job.status in [
        JobStatus.running,
        JobStatus.pending,
    ]:
        # restart tasks that have already been run
        for task in job.tasks:
            task.status = "skipped"

    db.commit()


@api_router.get(
    "/api/jobs/{job_id}/tasks", tags=["Jobs"], response_model=PaginatedResponse[Task]
)
def get_tasks(
    job_id: int,
    dao: Dao = Depends(get_dao),
    status: List[TaskStatus] = Query(
        [TaskStatus.created, TaskStatus.pending, TaskStatus.running]
    ),
    auth: authorization.Rules = Depends(get_rules),
    skip: int = 0,
    limit: int = PAGINATION_LIMIT,
    job: job_db_models.Job = Depends(get_job_or_fail),
):
    auth.assert_jobs(owner_id=job.owner_id)
    return dao.get_tasks(job.id, status, skip, limit)


def get_router():
    return api_router
