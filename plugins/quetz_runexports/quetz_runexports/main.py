import json
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

        if not version.runexports:
            metadata = db_models.PackageVersionMetadata(
                version_id=version.id, run_exports=run_exports
            )
            db.add(metadata)
        else:
            metadata = db.query(db_models.PackageVersionMetadata).get(version.id)
            metadata.run_exports = run_exports
        db.commit()
