import contextlib
import json
import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from http.client import IncompleteRead
from tempfile import SpooledTemporaryFile
from typing import List, Tuple, Union

import requests
from fastapi import HTTPException, status
from tenacity import TryAgain, retry
from tenacity.after import after_log
from tenacity.stop import stop_after_attempt
from tenacity.wait import wait_exponential

from quetz import authorization, rest_models
from quetz.condainfo import CondaInfo, get_subdir_compat
from quetz.config import Config
from quetz.dao import Dao
from quetz.db_models import Channel, PackageVersion
from quetz.errors import DBError
from quetz.pkgstores import PackageStore
from quetz.tasks import indexing
from quetz.utils import (
    MembershipAction,
    TicToc,
    add_static_file,
    check_package_membership,
)
from utils import parse_package_filename

# copy common subdirs from conda:
# https://github.com/conda/conda/blob/a78a2387f26a188991d771967fc33aa1fb5bb810/conda/base/constants.py#L63

KNOWN_SUBDIRS = (
    "noarch",
    "linux-32",
    "linux-64",
    "linux-aarch64",
    "linux-armv6l",
    "linux-armv7l",
    "linux-ppc64",
    "linux-ppc64le",
    "linux-s390x",
    "osx-64",
    "osx-arm64",
    "win-32",
    "win-64",
    "zos-z",
)


logger = logging.getLogger("quetz")


class RemoteRepository:
    """Resource object for external package repositories."""

    def __init__(self, host, session):
        self.host = host
        self.session = session

    def open(self, path):
        return RemoteFile(self.host, path, self.session)


class RemoteServerError(Exception):
    pass


class RemoteFileNotFound(RemoteServerError):
    pass


class RemoteFile:
    def __init__(self, host: str, path: str, session=None):
        if session is None:
            session_as_param = False
            session = requests.Session()
        else:
            session_as_param = True
        remote_url = os.path.join(host, path)
        try:
            response = session.get(remote_url, stream=True)
        except requests.ConnectionError:
            raise RemoteServerError
        if response.status_code == 404:
            raise RemoteFileNotFound
        elif response.status_code != 200:
            raise RemoteServerError
        self.file = SpooledTemporaryFile()
        response.raw.decode_content = True  # for gzipped response content
        shutil.copyfileobj(response.raw, self.file)
        response.close()
        if not session_as_param:
            session.close()

        # workaround for https://github.com/python/cpython/pull/3249
        if not hasattr(self.file, "seekable"):
            self.file.readable = self.file._file.readable  # type: ignore
            self.file.writable = self.file._file.writable  # type: ignore
            self.file.seekable = self.file._file.seekable  # type: ignore

        # rewind
        self.file.seek(0)
        _, self.filename = os.path.split(remote_url)
        self.content_type = response.headers.get("content-type")

    def json(self):
        return json.load(self.file)


def download_remote_file(
    repository: RemoteRepository, pkgstore: PackageStore, channel: str, path: str
):
    """Download a file from a remote repository to a package store"""

    # Check if a download is already underway for this file
    lock = pkgstore.get_download_lock(channel, path)
    if lock:
        # Wait for the download to complete
        lock.acquire()
        # Release the lock so that any other clients can also finish
        lock.release()
        return
    # Acquire a lock to prevent multiple concurrent downloads of the same file
    with pkgstore.create_download_lock(channel, path):
        logger.debug(f"Downloading {path} from {channel} to pkgstore")
        remote_file = repository.open(path)
        data_stream = remote_file.file

        if path.endswith('.json'):
            add_static_file(data_stream.read(), channel, None, path, pkgstore)
        else:
            pkgstore.add_package(data_stream, channel, path)

    pkgstore.delete_download_lock(channel, path)


@contextlib.contextmanager
def _check_checksum(dao: Dao, channel_name: str, platform: str, keyname="sha256"):
    """context manager to compare sha or md5 hashes"""

    # lazily load repodata on first request
    package_fingerprints = None

    def _func(package_name, metadata):
        nonlocal package_fingerprints

        if package_fingerprints is None:
            package_versions = (
                dao.db.query(PackageVersion)
                .filter(PackageVersion.channel_name == channel_name)
                .filter(PackageVersion.platform == platform)
                .all()
            )

            package_fingerprints = {}
            for v in package_versions:
                info = json.loads(v.info)
                package_fingerprints[v.filename] = info.get(keyname)

        if keyname not in metadata:
            return None

        new_checksum = metadata[keyname]
        if package_name in package_fingerprints:
            existing_checksum = package_fingerprints[package_name]
            if existing_checksum is None:
                # missing checksum
                is_uptodate = None
            else:
                # compare  checksum
                is_uptodate = existing_checksum == new_checksum
        else:
            # missing package version
            is_uptodate = False

        return is_uptodate

    yield _func


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    after=after_log(logger, logging.WARNING),
)
def download_file(remote_repository, path_metadata):
    path, package_name, metadata = path_metadata
    try:
        f = remote_repository.open(path)
    except RemoteServerError as e:
        logger.error(f"remote server error when getting a file {path}")
        raise e
    except IncompleteRead as e:
        logger.error(f"Incomplete read for {path}")
        raise e

    logger.debug(f"Fetched file {path}")
    return f, package_name, metadata


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    after=after_log(logger, logging.WARNING),
)
def _upload_package(file, channel_name, subdir, pkgstore):
    dest = os.path.join(subdir, file.filename)

    try:
        file.file.seek(0)
        logger.debug(
            f"uploading file {dest} from channel {channel_name} to package store"
        )
        pkgstore.add_package(file.file, channel_name, dest)

    except AttributeError as e:
        logger.error(f"Could not upload {file}, {file.filename}. {str(e)}")
        raise TryAgain


def handle_repodata_package(
    channel,
    files_metadata,
    dao,
    auth,
    force,
    pkgstore,
    config,
):
    from quetz.main import pm

    channel_name = channel.name
    proxylist = channel.load_channel_metadata().get('proxylist', [])
    user_id = auth.assert_user()

    # check package format and permissions, calculate total size
    total_size = 0
    for file, package_name, metadata in files_metadata:
        parts = file.filename.rsplit("-", 2)
        if len(parts) != 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"package file name has wrong format {file.filename}",
            )
        else:
            package_name = parts[0]
        auth.assert_upload_file(channel_name, package_name)
        if force:
            auth.assert_overwrite_package_version(channel_name, package_name)

        # workaround for https://github.com/python/cpython/pull/3249
        if type(file.file) is SpooledTemporaryFile and not hasattr(file, "seekable"):
            file.file.seekable = file.file._file.seekable

        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        total_size += size
        file.file.seek(0)

    # create package in database
    # channel_data = _load_remote_channel_data(remote_repository)
    # create_packages_from_channeldata(channel_name, user_id, channel_data, dao)

    # validate quota
    dao.assert_size_limits(channel_name, total_size)

    pkgstore.create_channel(channel_name)

    with TicToc("upload file without extracting"):
        nthreads = config.general_package_unpack_threads
        with ThreadPoolExecutor(max_workers=nthreads) as executor:
            for file, package_name, metadata in files_metadata:
                if proxylist and package_name in proxylist:
                    # skip packages that should only ever be proxied
                    continue
                subdir = get_subdir_compat(metadata)
                executor.submit(_upload_package, file, channel_name, subdir, pkgstore)

    with TicToc("add versions to the db"):
        for file, package_name, metadata in files_metadata:
            version = create_version_from_metadata(
                channel_name, user_id, package_name, metadata, dao
            )
            condainfo = CondaInfo(file.file, package_name, lazy=True)
            pm.hook.post_add_package_version(version=version, condainfo=condainfo)
            file.file.close()


def get_remote_repodata(
    channel_name: str, arch: str, remote_repository: RemoteRepository
) -> Union[dict, None]:
    """
    Fetches the repodata.json file from a remote repository
    for a given channel and architecture.

    The function tries to fetch two types of repodata files:
    "repodata_from_packages.json" and "repodata.json".
    If both files are not found or are not properly formatted,
    the function returns None.

    Args:
        channel_name (str)
        arch (str)
        remote_repository (RemoteRepository): remote repo to fetch from

    Returns:
        dict or None: A dictionary containing the repodata
            if the file is found and properly formatted, None otherwise.
    """
    repodata = {}
    for repodata_fn in ["repodata_from_packages.json", "repodata.json"]:
        try:
            repo_file = remote_repository.open(os.path.join(arch, repodata_fn))
            repodata = json.load(repo_file.file)
            return repodata
        except RemoteServerError:
            logger.error(
                f"can not get {repodata_fn} for channel {arch}/{channel_name}."
            )
            if repodata_fn == "repodata.json":
                logger.error(f"Giving up for {channel_name}/{arch}.")
                return None
            else:
                logger.error("Trying next filename.")
                continue
        except json.JSONDecodeError:
            logger.error(
                f"repodata.json badly formatted for arch {arch}"
                f"in channel {channel_name}"
            )
            if repodata_fn == "repodata.json":
                return None

    return {}


def sync_mirror(
    channel_name: str,
    remote_repository: RemoteRepository,
    arch: str,
    dao: Dao,
    pkgstore: PackageStore,
    auth: authorization.Rules,
    includelist: List[str] = None,
    excludelist: List[str] = None,
    skip_errors: bool = True,
    use_repodata: bool = False,
):
    """
    Synchronize a mirror channel with a remote repository.

    Args:
        channel_name: name of the channel to synchronize
        remote_repository: RemoteRepository object
        arch: architecture to synchronize
        dao: Dao object
        pkgstore
        auth
        includelist: list of package names to include
        excludelist: list of package names to exclude
        skip_errors: if True, continue processing packages even if an error occurs
        use_repodata: if True, use repodata.json to process packages

    """
    force = True  # needed for updating packages
    logger.info(
        f"Running channel mirroring {channel_name}/{arch} from {remote_repository.host}"
    )

    repodata = get_remote_repodata(channel_name, arch, remote_repository)
    if not repodata:
        return  # quit; error has already been logged.

    packages = repodata.get("packages", {})

    channel = dao.get_channel(channel_name)
    if not channel:
        logger.error(f"channel {channel_name} not found")
        return

    from quetz.main import handle_package_files

    packages = repodata.get("packages", {}) | repodata.get("packages.conda", {})

    version_methods = [
        _check_checksum(dao, channel_name, arch, "sha256"),
        _check_checksum(dao, channel_name, arch, "md5"),
    ]

    config = Config()
    max_batch_length = config.mirroring_batch_length
    max_batch_size = config.mirroring_batch_size
    # version_methods are context managers (for example, to update the db
    # after all packages have been checked), so we need to enter the context
    # for each
    any_updated = False
    with contextlib.ExitStack() as version_stack:
        version_checks = [
            version_stack.enter_context(method) for method in version_methods
        ]

        update_batch = []
        update_size = 0
        remove_batch = []

        def handle_batch(update_batch):
            # i_batch += 1
            logger.info(f"Handling batch: {[p[1] for p in update_batch]}")
            if not update_batch:
                return False

            remote_packages = []
            remote_packages_with_metadata = []

            with ThreadPoolExecutor(
                max_workers=config.mirroring_num_parallel_downloads
            ) as executor:
                for f in executor.map(
                    download_file,
                    (remote_repository,) * len(update_batch),
                    update_batch,
                ):
                    if f is not None:
                        remote_packages.append(f[0])
                        remote_packages_with_metadata.append(f)

            try:
                if use_repodata:
                    handle_repodata_package(
                        channel,
                        remote_packages_with_metadata,
                        dao,
                        auth,
                        force,
                        pkgstore,
                        config,
                    )

                else:
                    handle_package_files(
                        channel,
                        remote_packages,
                        dao,
                        auth,
                        force,
                        is_mirror_op=True,
                    )
                return True

            except Exception as exc:
                logger.error(
                    f"could not process package {update_batch} from channel"
                    f"{channel_name} due to error {exc} of "
                    f"type {exc.__class__.__name__}"
                )
                if not skip_errors:
                    raise exc

            return False

        # go through all packages from remote channel
        channel_metadata = channel.load_channel_metadata()
        for repo_package_name, metadata in packages.items():
            action = check_package_membership(
                channel,
                channel_metadata,
                repo_package_name,
                metadata,
                remote_host=remote_repository.host,
            )
            if action == MembershipAction.INCLUDE:
                # try to find out whether it's a new package version
                is_uptodate = None
                for _check in version_checks:
                    is_uptodate = _check(repo_package_name, metadata)
                    if is_uptodate is not None:
                        break

                # if package is up-to-date skip uploading file
                if is_uptodate:
                    continue

                logger.debug(f"updating package {repo_package_name} from {arch}")

                path = os.path.join(arch, repo_package_name)
                update_batch.append((path, repo_package_name, metadata))
                update_size += metadata.get('size', 100_000)
            elif action == MembershipAction.IGNORE:
                logger.debug(
                    f"package {repo_package_name} not needed by "
                    f"{remote_repository.host} but other channels"
                )
            else:
                logger.debug(
                    f"package {repo_package_name} not needed by "
                    f"{remote_repository.host} and no other channels."
                )
                remove_batch.append((arch, repo_package_name))

            # perform either downloads or removals
            if len(update_batch) >= max_batch_length or update_size >= max_batch_size:
                logger.debug(f"Executing batch with {update_size}")
                any_updated |= handle_batch(update_batch)
                update_batch.clear()
                update_size = 0

        # handle final batch
        any_updated |= handle_batch(update_batch)

        # remove packages marked for removal
        if remove_batch:
            any_updated |= remove_packages(remove_batch, channel, dao, pkgstore)

    if any_updated:
        # build local repodata
        indexing.update_indexes(dao, pkgstore, channel_name, subdirs=[arch])


def remove_packages(
    remove_batch: List[Tuple[str, str]],
    channel: Channel,
    dao: Dao,
    pkgstore: PackageStore,
) -> bool:
    """
    Remove packages from the channel and the package store.
    Args:
        remove_batch: list of (arch, repo_package_name) tuples
            e.g. [('linux-64', 'foo-1.0-0.tar.bz2'), ...]
        channel: the channel to remove packages from
        dao
        pkgstore
    Returns True if any removals were performed.
    """

    logger.debug(f"Removing {len(remove_batch)} packages: {remove_batch}")
    removal_performed = False

    for package_spec in set(p[1] for p in remove_batch):
        package_name, version, build_string = parse_package_filename(package_spec)
        dao.remove_package(package_name=package_name, channel_name=channel.name)
        if pkgstore.file_exists(channel.name, package_spec):
            pkgstore.delete_file(channel.name, destination=package_spec)
        removal_performed = True

    dao.cleanup_channel_db(channel.name)

    return removal_performed


def create_packages_from_channeldata(
    channel_name: str, user_id: bytes, channeldata: dict, dao: Dao
):
    packages = channeldata.get("packages", {})

    for package_name, metadata in packages.items():
        description = metadata.get("description", "")
        summary = metadata.get("summary", "")
        package_data = rest_models.Package(
            name=package_name,
            summary=summary,
            description=description,
        )

        try:
            package = dao.create_package(
                channel_name, package_data, user_id, role=authorization.OWNER
            )
        except DBError:
            # package already exists so skip it so we retrieve and update it
            package = dao.get_package(channel_name, package_name)
            if not package:
                raise KeyError(
                    f"Package '{package_name}' not found in channel {channel_name}"
                )
            package.description = description
            package.summary = summary
        package.url = metadata.get("home", "")
        package.platforms = ":".join(metadata.get("subdirs", []))
        package.channeldata = json.dumps(metadata)
        dao.db.commit()


def create_version_from_metadata(
    channel_name: str,
    user_id: bytes,
    package_file_name: str,
    package_data: dict,
    dao: Dao,
):
    package_name = package_data["name"]
    package = dao.get_package(channel_name, package_name)
    if not package:
        package_info = rest_models.Package(
            name=package_name,
            summary=package_data.get("summary", ""),
            description=package_data.get("description", ""),
        )
        dao.create_package(channel_name, package_info, user_id, "owner")

    if package_file_name.endswith(".conda"):
        pkg_format = "conda"
    elif package_file_name.endswith(".tar.bz2"):
        pkg_format = "tarbz2"
    else:
        raise ValueError(
            f"Unknown package format for package {package_file_name}"
            f"in channel {channel_name}"
        )
    version = dao.create_version(
        channel_name,
        package_name,
        pkg_format,
        get_subdir_compat(package_data),
        package_data["version"],
        int(package_data["build_number"]),
        package_data["build"],
        package_file_name,
        json.dumps(package_data),
        user_id,
        package_data["size"],
    )

    return version


def create_versions_from_repodata(
    channel_name: str, user_id: bytes, repodata: dict, dao: Dao
):
    packages = repodata.get("packages", {})
    for filename, metadata in packages.items():
        create_version_from_metadata(channel_name, user_id, filename, metadata, dao)


def _load_remote_channel_data(remote_repository: RemoteRepository) -> dict:
    """
    given the remote repository, load the channeldata.json file
    raises: HTTPException if the remote server is unavailable
    """
    try:
        channel_data = remote_repository.open("channeldata.json").json()
    except (RemoteFileNotFound, json.JSONDecodeError):
        channel_data = {}
    except RemoteServerError as e:
        logger.error(f"Remote server error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Remote channel {remote_repository.host} unavailable",
        )
    return channel_data


def synchronize_packages(
    channel_name: str,
    dao: Dao,
    pkgstore: PackageStore,
    auth: authorization.Rules,
    session: requests.Session,
    includelist: List[str] = None,
    excludelist: List[str] = None,
    use_repodata: bool = False,
):
    """synchronize package from a remote channel.

    Args:
        channel_name (str): the channel to be updated, e.g. the mirror channel
        dao (Dao): database access object
        pkgstore (PackageStore): the target channels package store
        use_repodata (bool, optional): wether to create packages from repodata.json
    """
    logger.info(f"executing synchronize_packages task in a process {os.getpid()}")

    new_channel = dao.get_channel(channel_name)

    if not new_channel:
        logger.error(f"channel {channel_name} not found")
        return

    for mirror_channel_url in new_channel.mirror_channel_urls:
        remote_repo = RemoteRepository(mirror_channel_url, session)

        user_id = auth.assert_user()

        channel_data = _load_remote_channel_data(remote_repo)
        subdirs = None
        if use_repodata and includelist is None and excludelist is None:
            create_packages_from_channeldata(channel_name, user_id, channel_data, dao)
            subdirs = channel_data.get("subdirs", [])

        # if no channel data use known architectures
        if subdirs is None:
            subdirs = KNOWN_SUBDIRS

        for arch in subdirs:
            sync_mirror(
                new_channel.name,
                remote_repo,
                arch,
                dao,
                pkgstore,
                auth,
                includelist,
                excludelist,
                use_repodata=use_repodata,
            )
