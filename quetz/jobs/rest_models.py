import logging
import pickle
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator

from .models import JobStatus, TaskStatus

logger = logging.getLogger("quetz")


class JobBase(BaseModel):
    """New job spec"""

    items_spec: str = Field(..., title='Item selector spec')
    manifest: str = Field(None, title='Name of the function')

    start_at: Optional[datetime] = Field(
        None, title="date and time the job should start, if None it starts immediately"
    )
    repeat_every_seconds: Optional[int] = Field(
        None,
        title=(
            "interval in seconds at which the job should be repeated, "
            "if None it is a one-off job"
        ),
    )


class JobUpdateModel(BaseModel):
    """Modify job spec items (status and items_spec)"""

    items_spec: str = Field(None, title='Item selector spec')
    status: JobStatus = Field(None, title='Change status')
    force: bool = Field(False, title="force re-running job on all matching packages")


class Job(JobBase):
    id: int = Field(None, title='Unique id for job')
    owner_id: uuid.UUID = Field(None, title='User id of the owner')

    created: datetime = Field(None, title='Created at')

    status: JobStatus = Field(None, title='Status of the job (running, paused, ...)')

    items_spec: str = Field(None, title='Item selector spec')

    @validator("manifest", pre=True)
    def convert_name(cls, v):
        try:
            try:
                func = pickle.loads(v)
                return f"{func.__module__}:{func.__name__}"
            except pickle.UnpicklingError:
                return v.decode('ascii')
        except ModuleNotFoundError as e:
            logger.error(f"job function not found: could not import module {e.name}")
            return e.name + ":undefined"

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
        if v:
            return {'filename': v.filename, 'id': uuid.UUID(bytes=v.id).hex}
        else:
            return {}

    class Config:
        orm_mode = True
