from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from quetz import db_models
from quetz.dao import Dao
from quetz.deps import get_dao, get_package_or_fail
from quetz.metrics import rest_models
from quetz.metrics.db_models import IntervalType

api_router = APIRouter(prefix="/metrics")


@api_router.get(
    "/channels/{channel_name}/packages/{package_name}/versions/{platform}/{filename}",  # noqa
    response_model=rest_models.PackageVersionMetricResponse,
    tags=["metrics"],
)
def get_package_version_metrics(
    platform: str,
    filename: str,
    package_name: str,
    channel_name: str,
    fill_zeros: bool = False,
    period: IntervalType = IntervalType.day,
    metric_name: str = "download",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    package: db_models.Package = Depends(get_package_or_fail),
    dao: Dao = Depends(get_dao),
):
    version = dao.get_package_version_by_filename(
        channel_name, package_name, filename, platform
    )

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"package version {platform}/{filename} not found",
        )

    series = dao.get_package_version_metrics(
        version.id, period, metric_name, start=start, end=end, fill_zeros=fill_zeros
    )

    total = sum(s.count for s in series)

    return {
        "server_timestamp": datetime.utcnow(),
        "period": period,
        "metric_name": metric_name,
        "total": total,
        "series": series,
    }


@api_router.get(
    "/channels/{channel_name}",
    response_model=rest_models.ChannelMetricResponse,
    tags=["metrics"],
)
def get_channel_metrics(
    channel_name: str,
    period: IntervalType = IntervalType.day,
    metric_name: str = "download",
    platform: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    dao: Dao = Depends(get_dao),
):

    metrics = dao.get_channel_metrics(
        channel_name, period, metric_name, platform=platform, start=start, end=end
    )

    return {
        "server_timestamp": datetime.utcnow(),
        "period": period,
        "metric_name": metric_name,
        "packages": metrics,
    }


def get_router():
    return api_router
