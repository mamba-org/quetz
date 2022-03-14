# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from datetime import datetime
from enum import Enum

import sqlalchemy as sa

from quetz.db_models import UUID, Base


class JobStatus(str, Enum):
    pending = "pending"
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"
    timeout = "timeout"
    cancelled = "cancelled"


class TaskStatus(str, Enum):
    created = "created"
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    skipped = "skipped"


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
    manifest = sa.Column(sa.LargeBinary(), nullable=False)
    owner_id = sa.Column(
        UUID, sa.ForeignKey("users.id", ondelete="cascade"), nullable=True
    )
    owner = sa.orm.relationship(
        "User", backref=sa.orm.backref("jobs", cascade="all,delete")
    )
    items_spec = sa.Column(sa.String(), nullable=True)
    items = sa.Column(
        sa.Enum(ItemsSelection),
        nullable=False,
        default=ItemsSelection.all,
    )
    status = sa.Column(
        sa.Enum(JobStatus),
        nullable=False,
        default=JobStatus.pending,
    )

    tasks = sa.orm.relationship(
        'Task', back_populates='job', cascade="all,delete-orphan", uselist=True
    )

    extra_args = sa.Column(sa.String(), nullable=True)

    start_at = sa.Column(sa.DateTime, nullable=True)
    repeat_every_seconds = sa.Column(sa.Integer, nullable=True)


class Task(Base):
    __tablename__ = "tasks"

    id = sa.Column(sa.Integer, primary_key=True)
    created = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    updated = sa.Column(sa.DateTime, nullable=False, default=datetime.utcnow)
    # name = sa.Column(sa.Unicode(256), nullable=False)
    status = sa.Column(
        sa.Enum(TaskStatus),
        nullable=False,
        default=TaskStatus.created,
    )
    job_id = sa.Column(
        sa.Integer, sa.ForeignKey("jobs.id", ondelete="cascade"), nullable=False
    )
    job = sa.orm.relationship("Job", back_populates='tasks')
    package_version_id = sa.Column(
        UUID, sa.ForeignKey("package_versions.id", ondelete="cascade"), nullable=True
    )
    package_version = sa.orm.relationship(
        "PackageVersion",
        backref=sa.orm.backref("tasks", cascade="all,delete-orphan"),
    )

    def __repr__(self):
        if self.package_version:
            filename = self.package_version.filename
        else:
            filename = None
        return (
            f"Task(id={self.id}, package_version='{filename},"
            f" job_id={self.job_id}')"
        )
