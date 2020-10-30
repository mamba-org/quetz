import json
import uuid
from contextlib import contextmanager

import quetz
from quetz.deps import get_db

from . import db_models
from .api import router

get_db = contextmanager(get_db)


@quetz.hookimpl
def register_router():
    return router


@quetz.hookimpl
def post_add_package_version(version, condainfo):
    run_exports = json.dumps(condainfo.run_exports)

    with get_db() as db:
        metadata = db_models.PackageVersionMetadata(
            id=uuid.uuid4().bytes, version_id=version.id, run_exports=run_exports
        )
        db.add(metadata)
        db.commit()
