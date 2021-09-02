import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.exc import IntegrityError

from quetz import authorization, rest_models
from quetz.condainfo import CondaInfo
from quetz.config import Config
from quetz.dao import Dao
from quetz.exceptions import PackageError

from .indexing import update_indexes

logger = logging.getLogger("quetz.tasks")


def uuid_to_bytes(id):

    if isinstance(id, str):
        id = uuid.UUID(id).bytes
    return id


def handle_condainfo(pkgstore, channel_name, fname):

    """Fetch CondaInfo for a package from pkgstaore"""

    fid = pkgstore.serve_path(channel_name, fname)

    try:
        condainfo = CondaInfo(fid, fname, lazy=False)
    except PackageError:
        logger.error(f"Package {fname} is not a tar.bzip2 file")
        condainfo = None

    return condainfo


def handle_file(channel_name, condainfo, dao, user_id):

    """Add or update conda package info to database"""

    filename = os.path.split(condainfo._filename)[-1]
    package_name = condainfo.info["name"]
    package_format = condainfo.package_format
    platform = condainfo.info["subdir"]
    version = condainfo.info["version"]
    build_number = condainfo.info["build_number"]
    build_string = condainfo.info["build"]
    size = condainfo.info["size"]
    info = json.dumps(condainfo.info)

    package = dao.get_package(channel_name, package_name)

    if not package:
        logger.debug(f"Creating package {package_name}")

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

        dao.update_package_channeldata(
            channel_name, package_name, condainfo.channeldata
        )

    try:
        logger.debug(
            f"Adding package {channel_name}/{platform}/{package_name}"
            + f"-{version}-{build_string}"
        )
        dao.create_version(
            channel_name=channel_name,
            package_name=package_name,
            package_format=package_format,
            platform=platform,
            version=version,
            build_number=build_number,
            build_string=build_string,
            size=size,
            filename=filename,
            info=info,
            uploader_id=user_id,
            upsert=True,
        )
        dao.db.commit()
    except IntegrityError:
        dao.rollback()
        logger.error(
            f"Duplicate package {channel_name}/{package_name}"
            + "-{condainfo.info['version']}"
        )
    dao.db.commit()


def chunks(lst, n):

    """Yield successive n-sized chunks from lst."""

    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def reindex_packages_from_store(
    dao: Dao, config: Config, channel_name: str, user_id, sync: bool = True
):
    """Reindex packages from files in the package store"""

    logger.debug(f"Re-indexing channel {channel_name}")

    channel = dao.get_channel(channel_name)
    pkg_db = []
    if channel:
        if not sync:
            for package in channel.packages:
                dao.db.delete(package)
            dao.db.commit()
        else:
            dao.cleanup_channel_db(channel_name)
            for package in channel.packages:
                for pv in package.package_versions:  # type: ignore
                    pkg_db.append(f"{pv.platform}/{pv.filename}")
            dao.db.commit()
    else:
        data = rest_models.Channel(
            name=channel_name, description="re-indexed from store", private=True
        )
        channel = dao.create_channel(data, user_id, authorization.OWNER)

    logger.debug(f"Reading package list for channel {channel_name}")
    user_id = uuid_to_bytes(user_id)
    pkgstore = config.get_package_store()
    all_files = pkgstore.list_files(channel_name)
    pkg_files = [f for f in all_files if f.endswith(".tar.bz2")]
    nthreads = config.general_package_unpack_threads

    logger.debug(f"Found {len(pkg_db)} packages for channel {channel_name} in database")
    logger.debug(
        f"Found {len(pkg_files)} packages for channel {channel_name} in pkgstore"
    )

    pkg_files = list(set(pkg_files) - set(pkg_db))
    logger.debug(
        f"Importing {len(pkg_files)} packages for channel {channel_name}"
        + " from pkgstore"
    )

    for pkg_group in chunks(pkg_files, nthreads * 8):
        tic = time.perf_counter()
        with ThreadPoolExecutor(max_workers=nthreads) as executor:
            results = []
            for fname in pkg_group:
                results.append(
                    executor.submit(handle_condainfo, pkgstore, channel_name, fname)
                )
            for future in as_completed(results):
                condainfo = future.result()
                if condainfo:
                    handle_file(channel_name, condainfo, dao, user_id)

        toc = time.perf_counter()
        logger.debug(
            f"Imported files {pkg_group[0]} to {pkg_group[-1]} "
            + f"for channel {channel_name} in {toc - tic:0.4f} seconds "
            + f"using {nthreads} threads"
        )

        try:
            update_indexes(dao, pkgstore, channel_name)
            dao.db.commit()
        except IntegrityError:
            dao.rollback()
            logger.error(f"Update index {channel_name} failed")
    dao.cleanup_channel_db(channel_name)
    dao.db.commit()
