import json

import quetz
from quetz.database import get_db_manager

from . import db_models
from .api import router


@quetz.hookimpl
def register_router():
    return router


@quetz.hookimpl
def post_add_package_version(version, condainfo):
    run_exports = json.dumps(condainfo.run_exports)

    with get_db_manager() as db:
        if not version.runexports:
            metadata = db_models.PackageVersionMetadata(
                version_id=version.id, data=run_exports
            )
            db.add(metadata)
        else:
            metadata = db.get(db_models.PackageVersionMetadata, version.id)
            if not metadata:
                raise KeyError(f"No metadata found for version '{version.id}'.")
            metadata.data = run_exports
        db.commit()
