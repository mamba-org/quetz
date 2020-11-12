import json
import os
from contextlib import contextmanager

from sqlalchemy import and_, func

import quetz
from quetz.db_models import PackageVersion
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
    subdir = condainfo.info["subdir"]

    for each_file in condainfo.files:
        if each_file.startswith(b"bin/"):
            command = each_file.split(b"bin/")[1].strip().decode("utf-8").split("/")[0]
            package = condainfo.info["name"]
            if command not in suggest_map:
                suggest_map[command] = package

    print(suggest_map)  # this works for the last test

    with get_db() as db:
        if not version.binfiles:
            metadata = db_models.CondaSuggestMetadata(
                version_id=version.id, data=json.dumps(suggest_map)
            )
            db.add(metadata)
        else:
            metadata = db.query(db_models.CondaSuggestMetadata).get(version.id)
            metadata.data = json.dumps(suggest_map)
        db.commit()
        generate_channel_suggest_map(db, version.channel_name, subdir)


def generate_channel_suggest_map(db, channel_name, subdir):
    subq = (
        db.query(
            PackageVersion.package_name,
            func.max(PackageVersion.version).label('max_version'),
        )
        .filter(PackageVersion.channel_name == channel_name)
        .filter(PackageVersion.platform == subdir)
        .group_by(PackageVersion.package_name)
        .subquery()
    )

    all_packages = (
        (
            db.query(PackageVersion)
            .filter(PackageVersion.channel_name == channel_name)
            .filter(PackageVersion.platform == subdir)
        )
        .join(
            subq,
            and_(
                PackageVersion.package_name == subq.c.package_name,
                PackageVersion.version == subq.c.max_version,
            ),
        )
        .all()
    )

    print(all_packages)  # this is empty for the last test i.e. []

    channel_suggest_map = {}

    for each_package in all_packages:
        if not each_package.binfiles:
            pass
        else:
            files_data = json.loads(each_package.binfiles.data)
            for (k, v) in files_data.items():
                channel_suggest_map[k] = v

    map_filename = "{0}.{1}.map".format(channel_name, subdir)
    map_filepath = os.path.join(os.getcwd(), "channels", channel_name, subdir)

    if not os.path.exists(map_filepath):
        os.makedirs(map_filepath)

    with open(os.path.join(map_filepath, map_filename), "w") as f:
        for (k, v) in sorted(channel_suggest_map.items()):
            f.write("{0}:{1}\n".format(k, v))
