import json
from contextlib import contextmanager

import quetz
from quetz.config import Config
from quetz.database import get_session

from . import db_models
from .api import router


@contextmanager
def get_db_manager():
    config = Config()

    db = get_session(config.sqlalchemy_database_url)

    try:
        yield db
    finally:
        db.close()


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
            metadata = db.query(db_models.PackageVersionMetadata).get(version.id)
            metadata.data = run_exports
        db.commit()
