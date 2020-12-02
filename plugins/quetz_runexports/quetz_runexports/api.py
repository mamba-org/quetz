import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm.session import Session

from quetz.db_models import PackageVersion
from quetz.deps import get_db

router = APIRouter()


@router.get(
    "/api/channels/{channel_name}/packages/{package_name}/versions/"
    "{platform}/{filename}/run_exports"
)
def get_run_exports(
    channel_name: str,
    package_name: str,
    platform: str,
    filename: str,
    db: Session = Depends(get_db),
):

    package_version = (
        db.query(PackageVersion)
        .filter(PackageVersion.channel_name == channel_name)
        .filter(PackageVersion.platform == platform)
        .filter(PackageVersion.filename == filename)
        .first()
    )

    if not package_version.runexports:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"run_exports for package {channel_name}/{platform}/{filename}"
                "not found"
            ),
        )
    run_exports = json.loads(package_version.runexports.data)
    return run_exports
