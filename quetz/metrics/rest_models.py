from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel, Field

from quetz.metrics.db_models import IntervalType


class PackageVersionMetricItem(BaseModel):
    timestamp: datetime
    count: int

    class Config:
        orm_mode = True


class PackageVersionMetricSeries(BaseModel):

    series: List[PackageVersionMetricItem]


class PackageVersionMetricResponse(PackageVersionMetricSeries):

    server_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        title="server timestamp at which the response was generated",
    )
    period: IntervalType
    metric_name: str
    total: int


class ChannelMetricResponse(BaseModel):
    server_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        title="server timestamp at which the response was generated",
    )
    period: IntervalType
    metric_name: str
    packages: Dict[str, PackageVersionMetricSeries]
