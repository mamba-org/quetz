from enum import Enum

import sqlalchemy as sa

from quetz.db_models import UUID, Base


class Interval(Enum):
    month = "M"
    year = "Y"
    day = "D"
    total = "T"


class PackageVersionMetric(Base):
    __tablename__ = "package_version_metrics"

    package_version_id = sa.Column(
        UUID, sa.ForeignKey("package_versions.id"), primary_key=True
    )

    metric_name = sa.Column(sa.String(255), nullable=False, primary_key=True)
    interval_type = sa.Column(sa.Enum(Interval), primary_key=True)
    count = sa.Column(sa.Integer, default=0, nullable=False)
    timestamp = sa.Column(sa.DateTime(), nullable=False, primary_key=True)

    package_version = sa.orm.relationship(
        "PackageVersion", backref=sa.orm.backref("metrics", cascade="all,delete-orphan")
    )

    def __repr__(self):
        return (
            f"PackageVersionMetric(metric_name={self.metric_name}, "
            f"interval_type={self.interval_type}, "
            f"timestamp={self.timestamp},count={self.count})"
        )
