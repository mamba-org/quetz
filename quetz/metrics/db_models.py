import uuid
from datetime import datetime, timedelta
from enum import Enum

import sqlalchemy as sa

from quetz.db_models import UUID, Base


class IntervalType(Enum):
    hour = "H"
    day = "D"
    month = "M"
    year = "Y"

    @property
    def timedelta(self):

        if self == IntervalType.hour:
            return timedelta(hours=1)
        if self == IntervalType.day:
            return timedelta(days=1)
        raise ValueError(f"can not create timedelta for interval '{self.name}'")


def round_timestamp(timestamp, period):
    """round timestamp to nearest period"""
    now_interval = timestamp.replace(minute=0, second=0, microsecond=0)
    if period in [IntervalType.day, IntervalType.month, IntervalType.year]:
        now_interval = now_interval.replace(hour=0)
    if period in [IntervalType.month, IntervalType.year]:
        now_interval = now_interval.replace(day=1)
    if period == IntervalType.year:
        now_interval = now_interval.replace(month=1)
    return now_interval


def next_timestamp(timestamp: datetime, interval: IntervalType):
    """next timestamp advanced by interval time"""
    if interval in [IntervalType.day, IntervalType.hour]:
        return timestamp + interval.timedelta
    if interval == IntervalType.month:
        if timestamp.month == 12:
            return timestamp.replace(year=timestamp.year + 1, month=1)
        else:
            return timestamp.replace(month=timestamp.month + 1)
    if interval == IntervalType.year:
        return timestamp.replace(year=timestamp.year + 1)
    raise ValueError(f"interval {interval.name} not supported")


class PackageVersionMetric(Base):
    __tablename__ = "aggregated_metrics"

    id = sa.Column(UUID, default=lambda: uuid.uuid4().bytes, primary_key=True)

    channel_name = sa.Column(sa.String)
    platform = sa.Column(sa.String)

    filename = sa.Column(sa.String)

    metric_name = sa.Column(sa.String(255), nullable=False)
    period = sa.Column(sa.Enum(IntervalType))
    count = sa.Column(sa.Integer, server_default=sa.text("0"), nullable=False)
    timestamp = sa.Column(sa.DateTime(), nullable=False)

    __table_args__ = (
        sa.Index(
            'package_version_metric_index',
            channel_name,
            platform,
            filename,
            metric_name,
            period,
            timestamp,
        ),
        sa.UniqueConstraint(
            channel_name,
            platform,
            filename,
            metric_name,
            period,
            timestamp,
            name="package_version_metric_constraint",
        ),
    )

    def __repr__(self):
        return (
            f"PackageVersionMetric(metric_name={self.metric_name}, "
            f"period={self.period.value}, "
            f"timestamp={self.timestamp},count={self.count})"
        )
