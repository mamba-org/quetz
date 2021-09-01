import logging
import pickle
import uuid
from datetime import datetime
from typing import Optional

from importlib_metadata import entry_points as get_entry_points
from pydantic import BaseModel, Field, validator

from . import handlers
from .models import JobStatus, TaskStatus

logger = logging.getLogger("quetz")


def parse_job_manifest(function_name):
    """validate and parse job function name from a string

    Examples:

    parse_job_manifest("some_function")

       returns one of the built-in functions registered in quetz.jobs.handlers modules

    parse_job_manifest("plugin:function_name")

       returns a function from a moduled registered with plugin's quetz.jobs entrypoint

    parse_job_manifest("non_existent_function")

       raises ValueError for unknown functions

    """
    paths = function_name.split(":")

    if len(paths) == 2:
        plugin_name, job_name = paths
        entry_points = tuple(
            get_entry_points().select(group='quetz.jobs', name=plugin_name)
        )
        if not entry_points:
            raise ValueError(
                f"invalid function {function_name}: "
                f"plugin {plugin_name} not installed"
            )
        job_module = entry_points[0].load()
        try:
            return getattr(job_module, job_name)
        except AttributeError:
            raise ValueError(
                f"invalid function '{job_name}' name in plugin '{plugin_name}'"
            )
    elif len(paths) == 1:
        try:
            return handlers.JOB_HANDLERS[function_name]
        except KeyError:
            raise ValueError(
                f"invalid function {function_name}: no such built-in function,"
                " please provide plugin name"
            )
    else:
        raise ValueError(f"invalid function {function_name} - could not parse")


def parse_job_name(v):

    try:
        return v.decode("ascii")
    except UnicodeDecodeError:
        pass

    # try unpickling

    try:
        func = pickle.loads(v)
        return f"{func.__module__}:{func.__name__}"
    except pickle.UnpicklingError:
        raise ValueError("could not parse manifest")
    except ModuleNotFoundError as e:
        logger.error(f"job function not found: could not import module {e.name}")
        return f"{e.name}:undefined"


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

    @validator("manifest", pre=True)
    def validate_job_name(cls, function_name):

        if isinstance(function_name, bytes):
            return parse_job_name(function_name)

        parse_job_manifest(function_name)

        return function_name.encode('ascii')


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
