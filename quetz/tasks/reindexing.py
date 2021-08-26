import json
import logging
import os
import uuid

from sqlalchemy.exc import IntegrityError

from quetz import authorization, rest_models
from quetz.condainfo import CondaInfo
from quetz.config import Config
from quetz.dao import Dao

from .indexing import update_indexes

logger = logging.getLogger("quetz.tasks")


def uuid_to_bytes(id):
    if isinstance(id, str):
        id = uuid.UUID(id).bytes
    return id


def handle_file(channel_name, filename, file_buffer, dao, user_id):

    logger.debug(f"adding file '{filename}' to channel '{channel_name}'")
    user_id = uuid_to_bytes(user_id)
    condainfo = CondaInfo(file_buffer, filename)

    package_name = condainfo.info["name"]

    package = dao.get_package(channel_name, package_name)

    if not package:
        dao.create_package(
            channel_name,
            rest_models.Package(
                name=package_name,
                summary=condainfo.about.get("summary", "n/a"),
                description=condainfo.about.get("description", "n/a"),
            ),
            user_id,
            authorization.OWNER,
        )

    # Update channeldata info
    dao.update_package_channeldata(channel_name, package_name, condainfo.channeldata)

    filename = os.path.split(filename)[-1]

    try:
        version = dao.create_version(
            channel_name=channel_name,
            package_name=package_name,
            package_format=condainfo.package_format,
            platform=condainfo.info["subdir"],
            version=condainfo.info["version"],
            build_number=condainfo.info["build_number"],
            build_string=condainfo.info["build"],
            size=condainfo.info["size"],
            filename=filename,
            info=json.dumps(condainfo.info),
            uploader_id=user_id,
            upsert=False,
        )
    except IntegrityError:
        logger.error(f"duplicate package '{package_name}' in channel '{channel_name}'")
        raise

    return version


def reindex_packages_from_store(dao: Dao, config: Config, channel_name: str, user_id):
    """Reindex packages from files in the package store"""

    db = dao.db
    user_id = uuid_to_bytes(user_id)

    pkgstore = config.get_package_store()

    all_files = pkgstore.list_files(channel_name)
    pkg_files = [f for f in all_files if f.endswith(".tar.bz2")]

    channel = dao.get_channel(channel_name)

    if channel:
        for package in channel.packages:
            db.delete(package)
        db.commit()
    else:
        data = rest_models.Channel(
            name=channel_name, description="re-indexed from files", private=True
        )
        channel = dao.create_channel(data, user_id, authorization.OWNER)

    for fname in pkg_files:
        fid = pkgstore.serve_path(channel_name, fname)
        handle_file(channel_name, fname, fid, dao, user_id)
    update_indexes(dao, pkgstore, channel_name)
