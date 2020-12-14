from datetime import datetime
from enum import Enum

import sqlalchemy as sa

from quetz.db_models import UUID, Base


class JobStatus(Enum):
    pending = 'pending'
    queued = 'queued'
    running = 'running'
    success = 'success'
    failed = 'failed'
    timeout = 'timeout'
    cancelled = 'cancelled'


class TaskStatus(Enum):
    pending = 'pending'
    running = 'running'
    success = 'success'
    failed = 'failed'
    skipped = 'skipped'


class ItemsSelection(Enum):
    watch = "watch"
    watch_for = "watch_for"
    all = "all"
    list = "list"


class Job(Base):
    __tablename__ = "jobs"

    id = sa.Column(sa.Integer, primary_key=True)
    created = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    updated = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    manifest = sa.Column(sa.Binary(), nullable=False)
    owner_id = sa.Column(UUID, sa.ForeignKey('users.id'), nullable=True)
    owner = sa.orm.relationship('User', backref=sa.orm.backref('jobs'))
    item_specs = sa.Column(sa.String(), nullable=True)
    items = sa.Column(
        sa.Enum(ItemsSelection),
        nullable=False,
        default=ItemsSelection.all,
    )
    # job_group_id = sa.Column(sa.Integer, sa.ForeignKey('job_group.id'))
    # job_group = sa.orm.relationship('JobGroup', backref=sa.orm.backref('jobs'))
    # secrets = sa.Column(sa.Boolean, nullable=False, server_default="t")
    # note = sa.Column(sa.Unicode(4096))
    # tags = sa.Column(sa.String())
    # runner = sa.Column(sa.String)
    status = sa.Column(
        sa.Enum(JobStatus),
        nullable=False,
        default=JobStatus.pending,
    )


class Task(Base):
    __tablename__ = 'tasks'

    id = sa.Column(sa.Integer, primary_key=True)
    created = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    updated = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    # name = sa.Column(sa.Unicode(256), nullable=False)
    status = sa.Column(
        sa.Enum(TaskStatus),
        nullable=False,
        default=TaskStatus.pending,
    )
    job_id = sa.Column(sa.Integer, sa.ForeignKey("jobs.id"), nullable=False)
    job = sa.orm.relationship("Job", backref=sa.orm.backref("tasks"))
    package_version_id = sa.Column(
        UUID, sa.ForeignKey("package_versions.id"), nullable=True
    )
    package_version = sa.orm.relationship(
        "PackageVersion", backref=sa.orm.backref("tasks")
    )
