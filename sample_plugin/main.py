import json
import uuid
from contextlib import contextmanager

import db_models
from fastapi import APIRouter

import quetz
from quetz.db_models import PackageVersion


@quetz.hookimpl
def register_router():
    router = APIRouter()

    @router.get(
        "/api/channels/{channel_name}/packages/{package_name}/versions/{version_hash}/run_exports"  # noqa
    )
    def get_plugin(channel_name, package_name, version_hash):

        version_id, build_string = version_hash.split("-")

        from quetz.main import get_db

        get_db = contextmanager(get_db)
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

    return router


@quetz.hookimpl
def post_add_package_version(version, condainfo):
    run_exports = json.dumps(condainfo.run_exports)
    from quetz.main import get_db

    with contextmanager(get_db)() as db:
        metadata = db_models.PackageVersionMetadata(
            id=uuid.uuid4().bytes, version_id=version.id, run_exports=run_exports
        )
        db.add(metadata)
        db.commit()
