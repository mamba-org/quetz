from enum import Enum

import sqlalchemy as sa

from quetz.db_models import UUID, Base


class IntervalType(Enum):
    hour = "H"
    day = "D"
    month = "M"
    year = "Y"


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


class PackageVersionMetric(Base):
    __tablename__ = "package_version_metrics"

    package_version_id = sa.Column(
        UUID, sa.ForeignKey("package_versions.id"), primary_key=True
    )

    metric_name = sa.Column(sa.String(255), nullable=False, primary_key=True)
    period = sa.Column(sa.Enum(IntervalType), primary_key=True)
    count = sa.Column(sa.Integer, server_default=sa.text("0"), nullable=False)
    timestamp = sa.Column(sa.DateTime(), nullable=False, primary_key=True)

    package_version = sa.orm.relationship(
        "PackageVersion", backref=sa.orm.backref("metrics", cascade="all,delete-orphan")
    )

    def __repr__(self):
        return (
            f"PackageVersionMetric(metric_name={self.metric_name}, "
            f"period={self.period.value}, "
            f"timestamp={self.timestamp},count={self.count})"
        )
