import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm.session import Session

from quetz.db_models import PackageVersion
from quetz.deps import get_db

router = APIRouter()


@router.get(
    "/api/channels/{channel_name}/packages/{package_name}/versions/{version_hash}/run_exports"  # noqa
)
def get_run_exports(
    channel_name, package_name, version_hash, db: Session = Depends(get_db)
):

    version_id, build_string = version_hash.split("-")

    package_version = (
        db.query(PackageVersion)
        .filter(PackageVersion.channel_name == channel_name)
        .filter(PackageVersion.version == version_id)
        .filter(PackageVersion.build_string == build_string)
        .first()
    )
    run_exports = json.loads(package_version.runexports.run_exports)
    return run_exports
