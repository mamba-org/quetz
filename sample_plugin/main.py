import json
import uuid
from contextlib import contextmanager

import db_models
from api import router

import quetz


@quetz.hookimpl
def register_router():
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
