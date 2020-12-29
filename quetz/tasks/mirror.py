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
from fastapi.responses import FileResponse, StreamingResponse
from tenacity import after_log, retry, stop_after_attempt, wait_exponential

from quetz import authorization
from quetz.config import Config
from quetz.dao import Dao
from quetz.db_models import Channel, PackageVersion
from quetz.pkgstores import PackageStore
from quetz.tasks import indexing
from quetz.utils import check_package_membership

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


def get_from_cache_or_download(
    repository, cache, target, exclude=["repodata.json", "current_respodata.json"]
):
    """Serve from cache or download if missing."""

    _, filename = os.path.split(target)
    skip_cache = filename in exclude

    chunksize = 10000

    def data_iter(f):
        chunk = f.read(chunksize)
        while chunk:
            yield chunk
            # Do stuff with byte.
            chunk = f.read(chunksize)

    if skip_cache:
        remote_file = repository.open(target)
        data_stream = remote_file.file

        return StreamingResponse(data_iter(data_stream))

    if target not in cache:
        # copy from repository to cache
        remote_file = repository.open(target)
        data_stream = remote_file.file
        cache.dump(target, data_stream)

    return FileResponse(cache[target])


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
            session = requests.Session()
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


class LocalCache:
    """Local storage for downloaded files."""

    def __init__(self, channel_name: str):
        self.cache_dir = "cache"
        self.channel = channel_name

    def dump(self, path, stream):
        cache_path = self._make_path(path)
        package_dir, _ = os.path.split(cache_path)
        os.makedirs(package_dir, exist_ok=True)
        with open(cache_path, "wb") as fid:
            shutil.copyfileobj(stream, fid)

    def __contains__(self, path):
        cache_path = self._make_path(path)
        return os.path.isfile(cache_path)

    def _make_path(self, path):
        cache_path = os.path.join(self.cache_dir, self.channel, path)
        return cache_path

    def __getitem__(self, path):

        cache_path = os.path.join(self.cache_dir, self.channel, path)

        if not os.path.isfile(cache_path):
            raise KeyError

        return cache_path


@contextlib.contextmanager
def _check_timestamp(channel: Channel, dao: Dao):
    """context manager for comparing the package timestamp
    last synchroninsation timestamp saved in quetz database."""

    last_synchronization = channel.timestamp_mirror_sync
    last_timestamp = 0

    def _func(package_name, metadata):

        if "time_modified" not in metadata:
            return None

        # use nonlocal to be able to modified last_timestamp in the
        # outer scope
        nonlocal last_timestamp
        time_modified = metadata["time_modified"]
        last_timestamp = max(time_modified, last_timestamp)

        # if channel was never synchronised we can't determine
        # whether the package is up-to-date from the timestamp
        is_uptodate = (
            time_modified <= last_synchronization if last_synchronization else None
        )
        if is_uptodate is not None:
            logger.debug(f"comparing synchronisation timestamps of {package_name}")
        return is_uptodate

    yield _func

    # after we are done, we need to update the last_synchronisation
    # in the db
    sync_timestamp = max(last_synchronization, last_timestamp)
    dao.update_channel(channel.name, {"timestamp_mirror_sync": sync_timestamp})


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

            # logger.debug(
            #     f"Got {len(package_versions)} existing packages for "
            #     f"{channel_name} / {platform}"
            # )
            package_fingerprints = set()
            for v in package_versions:
                info = json.loads(v.info)
                package_fingerprints.add((v.filename, info[keyname]))

        # use nonlocal to be able to modified last_timestamp in the
        # outer scope
        if keyname not in metadata:
            return None

        fingerprint = (package_name, metadata[keyname])
        is_uptodate = fingerprint in package_fingerprints

        return is_uptodate

    yield _func


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    after=after_log(logger, logging.WARNING),
)
def download_file(remote_repository, path):
    try:
        f = remote_repository.open(path)
    except RemoteServerError as e:
        logger.error(f"remote server error when getting a file {path}")
        raise e
    except IncompleteRead as e:
        logger.error(f"Incomplete read for {path}")
        raise e

    logger.debug(f"Fetched file {path}")
    return f


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

    from quetz.main import handle_package_files

    packages = repodata.get("packages", {})

    version_methods = [
        _check_timestamp(channel, dao),
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

            with ThreadPoolExecutor(
                max_workers=config.mirroring_num_parallel_downloads
            ) as executor:
                for f in executor.map(
                    download_file,
                    (remote_repository,) * len(update_batch),
                    update_batch,
                ):
                    if f is not None:
                        remote_packages.append(f)

            try:
                handle_package_files(
                    channel_name,
                    remote_packages,
                    dao,
                    auth,
                    force,
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

                update_batch.append(path)
                update_size += metadata.get('size', 100_000)

            if len(update_batch) >= max_batch_length or update_size >= max_batch_size:
                logger.debug(f"Executing batch with {update_size}")
                any_updated |= handle_batch(update_batch)
                update_batch = []
                update_size = 0

        # handle final batch
        any_updated |= handle_batch(update_batch)

    if any_updated:
        indexing.update_indexes(dao, pkgstore, channel_name, subdirs=[arch])


def synchronize_packages(
    channel_name: str,
    dao: Dao,
    pkgstore: PackageStore,
    auth: authorization.Rules,
    session: requests.Session,
    includelist: List[str] = None,
    excludelist: List[str] = None,
):

    logger.debug(f"executing synchronize_packages task in a process {os.getpid()}")

    new_channel = dao.get_channel(channel_name)

    host = new_channel.mirror_channel_url

    remote_repo = RemoteRepository(new_channel.mirror_channel_url, session)
    try:
        channel_data = remote_repo.open("channeldata.json").json()
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
        )
