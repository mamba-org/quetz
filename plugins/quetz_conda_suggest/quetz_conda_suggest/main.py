import json

from sqlalchemy import and_, func

import quetz
from quetz.config import Config
from quetz.database import get_db_manager
from quetz.db_models import PackageVersion
from quetz.utils import add_entry_for_index

from . import db_models
from .api import router

config = Config()
pkgstore = config.get_package_store()


@quetz.hookimpl
def register_router():
    return router


@quetz.hookimpl
def post_package_indexing(tempdir, channel_name, subdirs, files, packages):
    for subdir in subdirs:
        fname = f"{channel_name}.{subdir}.map"
        try:
            f = pkgstore.serve_path(channel_name, f"{subdir}/{fname}")
            data_bytes = f.read()

            add_entry_for_index(files, subdir, fname, data_bytes)
        except FileNotFoundError:
            pass


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

    with get_db_manager() as db:
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

    channel_suggest_map = {}

    for each_package in all_packages:
        if not each_package.binfiles:
            pass
        else:
            files_data = json.loads(each_package.binfiles.data)
            for k, v in files_data.items():
                channel_suggest_map[k] = v

    fname = f"{channel_name}.{subdir}.map"
    path = f"{subdir}/{fname}"
    data_bytes = (
        "\n".join(f"{k}:{v}" for (k, v) in sorted(channel_suggest_map.items())) + "\n"
    ).encode("utf-8")

    pkgstore.add_file(data_bytes, channel_name, path)
