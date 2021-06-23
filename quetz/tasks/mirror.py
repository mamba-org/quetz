import contextlib
import json
import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from http.client import IncompleteRead
from tempfile import SpooledTemporaryFile
from typing import List

import requests
from fastapi import HTTPException, status
from tenacity import TryAgain, after_log, retry, stop_after_attempt, wait_exponential

from quetz import authorization, rest_models
from quetz.condainfo import CondaInfo, get_subdir_compat
from quetz.config import Config
from quetz.dao import Dao
from quetz.db_models import PackageVersion
from quetz.errors import DBError
from quetz.pkgstores import PackageStore
from quetz.tasks import indexing
from quetz.utils import TicToc, check_package_membership

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

    dao.assert_size_limits(channel_name, total_size)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        after=after_log(logger, logging.WARNING),
    )
    def _upload_package(file, channel_name, subdir):

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

    pkgstore.create_channel(channel_name)
    nthreads = config.general_package_unpack_threads

    with TicToc("upload file without extracting"):
        with ThreadPoolExecutor(max_workers=nthreads) as executor:
            for file, package_name, metadata in files_metadata:
                if proxylist and package_name in proxylist:
                    # skip packages that should only ever be proxied
                    continue
                subdir = get_subdir_compat(metadata)
                executor.submit(_upload_package, file, channel_name, subdir)

    with TicToc("add versions to the db"):
        for file, package_name, metadata in files_metadata:
            version = create_version_from_metadata(
                channel_name, user_id, package_name, metadata, dao
            )
            condainfo = CondaInfo(file.file, package_name, lazy=True)
            pm.hook.post_add_package_version(version=version, condainfo=condainfo)
            file.file.close()


def initial_sync_mirror(
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

    force = True  # needed for updating packages

    for repodata_fn in ["repodata_from_packages.json", "repodata.json"]:
        try:
            repo_file = remote_repository.open(os.path.join(arch, repodata_fn))
            repodata = json.load(repo_file.file)
            break
        except RemoteServerError:
            logger.error(
                f"can not get {repodata_fn} for channel {arch}/{channel_name}."
            )
            if repodata_fn == "repodata.json":
                logger.error(f"Giving up for {channel_name}/{arch}.")
                return
            else:
                logger.error("Trying next filename.")
                continue
        except json.JSONDecodeError:
            logger.error(
                f"repodata.json badly formatted for arch {arch}"
                f"in channel {channel_name}"
            )
            if repodata_fn == "repodata.json":
                return

    channel = dao.get_channel(channel_name)

    if not channel:
        logger.error(f"channel {channel_name} not found")
        return

    from quetz.main import handle_package_files

    packages = repodata.get("packages", {})

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

        def handle_batch(update_batch):
            # i_batch += 1
            logger.debug(f"Handling batch: {update_batch}")
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

        for package_name, metadata in packages.items():
            if check_package_membership(package_name, includelist, excludelist):
                path = os.path.join(arch, package_name)

                # try to find out whether it's a new package version

                is_uptodate = None
                for _check in version_checks:
                    is_uptodate = _check(package_name, metadata)
                    if is_uptodate is not None:
                        break

                # if package is up-to-date skip uploading file
                if is_uptodate:
                    continue
                else:
                    logger.debug(f"updating package {package_name} from {arch}")

                update_batch.append((path, package_name, metadata))
                update_size += metadata.get('size', 100_000)

            if len(update_batch) >= max_batch_length or update_size >= max_batch_size:
                logger.debug(f"Executing batch with {update_size}")
                any_updated |= handle_batch(update_batch)
                update_batch.clear()
                update_size = 0

        # handle final batch
        any_updated |= handle_batch(update_batch)

    if any_updated:
        indexing.update_indexes(dao, pkgstore, channel_name, subdirs=[arch])


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

    pkg_format = "tarbz2" if package_file_name.endswith(".tar.bz2") else ".conda"
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

    logger.debug(f"executing synchronize_packages task in a process {os.getpid()}")

    new_channel = dao.get_channel(channel_name)

    if not new_channel:
        logger.error(f"channel {channel_name} not found")
        return

    host = new_channel.mirror_channel_url

    remote_repo = RemoteRepository(new_channel.mirror_channel_url, session)

    user_id = auth.assert_user()

    try:
        channel_data = remote_repo.open("channeldata.json").json()
        if use_repodata:
            create_packages_from_channeldata(channel_name, user_id, channel_data, dao)
        subdirs = channel_data.get("subdirs", [])
    except (RemoteFileNotFound, json.JSONDecodeError):
        subdirs = None
    except RemoteServerError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Remote channel {host} unavailable",
        )
    # if no channel data use known architectures
    if subdirs is None:
        subdirs = KNOWN_SUBDIRS

    for arch in subdirs:
        initial_sync_mirror(
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
