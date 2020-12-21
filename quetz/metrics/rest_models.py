from datetime import datetime
from typing import List

from pydantic import BaseModel

from quetz.metrics.db_models import IntervalType


class PackageVersionMetricItem(BaseModel):
    timestamp: datetime
    count: int

    class Config:
        orm_mode = True


class PackageVersionMetricSeries(BaseModel):

    period: IntervalType
    metric_name: str
    total: int
    series: List[PackageVersionMetricItem]
