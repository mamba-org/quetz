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
    suggest_map = {}
    files_listing = condainfo.files

    for each_file in files_listing:
        if each_file.startswith(b"bin/"):
            command = each_file.split(b"bin/")[1].strip().decode("utf-8").split("/")[0]
            package = condainfo.info["name"]
            if command not in suggest_map:
                suggest_map[command] = package

    with get_db() as db:
        if not version.files:
            metadata = db_models.CondaSuggestMetadata(
                version_id=version.id, data=json.dumps(suggest_map)
            )
            db.add(metadata)
        else:
            metadata = db.query(db_models.CondaSuggestMetadata).get(version.id)
            metadata.data = json.dumps(suggest_map)
        db.commit()
