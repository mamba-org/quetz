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
from .runner import run_jobs

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
    auth.assert_jobs()
    return dao.get_jobs(states=status, skip=skip, limit=limit)


@api_router.post("/api/jobs", tags=["Jobs"], status_code=201, response_model=Job)
def create_job(
    job: JobBase,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    """create a new job"""
    user = auth.assert_user()
    auth.assert_jobs()
    new_job = dao.create_job(user, job.manifest, job.items_spec)
    return new_job


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


@api_router.get("/api/jobs/{job_id}", tags=["Jobs"], response_model=Job)
def get_job(
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
    job: job_db_models.Job = Depends(get_job_or_fail),
):
    auth.assert_jobs()
    return job


@api_router.patch("/api/jobs/{job_id}", tags=["Jobs"])
def update_job(
    job_data: JobUpdateModel,
    db=Depends(get_db),
    job: job_db_models.Job = Depends(get_job_or_fail),
    auth: authorization.Rules = Depends(get_rules),
):
    """refresh job (re-run on new packages)"""
    auth.assert_jobs()
    job.status = job_data.status  # type: ignore

    # ignore tasks that have already been run
    if job_data.force:
        run_jobs(db, job_id=job.id, force=True)

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
):
    auth.assert_jobs()
    return dao.get_tasks(job_id, status, skip, limit)


def get_router():
    return api_router
