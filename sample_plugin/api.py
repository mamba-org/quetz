import json
from contextlib import contextmanager

from fastapi import APIRouter

from quetz.db_models import PackageVersion
from quetz.deps import get_db

router = APIRouter()

get_db = contextmanager(get_db)


@router.get(
    "/api/channels/{channel_name}/packages/{package_name}/versions/{version_hash}/run_exports"  # noqa
)
def get_plugin(channel_name, package_name, version_hash):

    version_id, build_string = version_hash.split("-")

    with get_db() as db:
        package_version = (
            db.query(PackageVersion)
            .filter(PackageVersion.channel_name == channel_name)
            .filter(PackageVersion.version == version_id)
            .filter(PackageVersion.build_string == build_string)
            .first()
        )
        run_exports = json.loads(package_version.runexports.run_exports)
    return run_exports
