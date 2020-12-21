from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel

from quetz.metrics.db_models import IntervalType


class PackageVersionMetricItem(BaseModel):
    timestamp: datetime
    count: int

    class Config:
        orm_mode = True


class PackageVersionMetricSeries(BaseModel):

    series: List[PackageVersionMetricItem]


class PackageVersionMetricResponse(PackageVersionMetricSeries):

    period: IntervalType
    metric_name: str
    total: int


class ChannelMetricResponse(BaseModel):
    period: IntervalType
    metric_name: str
    packages: Dict[str, PackageVersionMetricSeries]
