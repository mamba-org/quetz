import contextlib
import json
import os
import shutil
from tempfile import SpooledTemporaryFile

import requests
from fastapi import HTTPException, status
from fastapi.background import BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse

from quetz import authorization, indexing
from quetz.dao import Dao
from quetz.pkgstores import PackageStore

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
    """Ressource object for external package repositories."""

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
def _check_with_timestamp(channel, dao: Dao):
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
        is_uptodate = time_modified <= last_synchronization
        last_timestamp = max(time_modified, last_timestamp)
        return is_uptodate

    yield _func

    # after we are done, we need to update the last_synchronisation
    # in the db
    last_synchronisation = max(last_synchronization, last_timestamp)
    dao.update_channel(channel.name, {"timestamp_mirror_sync": last_synchronisation})


@contextlib.contextmanager
def _check_checksum(
    pkgstore: PackageStore, channel_name: str, arch: str, keyname="sha256"
):
    """context manager to compare sha hashes"""

    # lazily load repodata on first request
    local_repodata = None
    package_fingerprints = []

    def _func(package_name, metadata):
        # use nonlocal to be able to modified last_timestamp in the
        # outer scope
        if keyname not in metadata:
            return None

        nonlocal local_repodata
        if not local_repodata:
            try:
                fid = pkgstore.serve_path(
                    channel_name, os.path.join(arch, 'repodata.json')
                )
            except FileNotFoundError:
                # no packages for this platform locally, need to add package version
                local_repodata = True
                return False
            local_repodata = json.load(fid)
            fid.close()
            for local_package, local_metadata in local_repodata.get(
                "packages", []
            ).items():
                package_fingerprints.append((local_package, local_metadata[keyname]))

        fingerprint = (package_name, metadata[keyname])
        is_uptodate = fingerprint in package_fingerprints

        return is_uptodate

    yield _func


def initial_sync_mirror(
    channel_name: str,
    remote_repository: RemoteRepository,
    arch: str,
    dao: Dao,
    pkgstore: PackageStore,
    auth: authorization.Rules,
    background_tasks: BackgroundTasks,
    skip_errors: bool = True,
):

    force = True  # needed for updating packages

    try:
        repo_file = remote_repository.open(os.path.join(arch, "repodata.json"))
        repodata = json.load(repo_file.file)
    except RemoteServerError:
        # LOG: can not get repodata.json for channel {channel_name}
        return
    except json.JSONDecodeError:
        # LOG: repodata.json badly formatted for arch {arch} in channel {channel_name}
        return

    channel = dao.get_channel(channel_name)

    from quetz.main import handle_package_files

    packages = repodata.get("packages", {})
    with _check_with_timestamp(channel, dao) as _check_timestamp, _check_checksum(
        pkgstore, channel_name, arch, keyname="sha256"
    ) as _check_sha, _check_checksum(pkgstore, channel_name, arch, "md5") as _check_md5:
        for package_name, metadata in packages.items():
            path = os.path.join(arch, package_name)

            # try to find out whether it's a new package version
            checker_funcs = [_check_timestamp, _check_sha, _check_md5]

            is_uptodate = None
            for _check in checker_funcs:
                is_uptodate = _check(package_name, metadata)
                if is_uptodate is not None:
                    break

            # if package is up-to-date skip uploading file
            if is_uptodate:
                print(f"package {package_name} from {arch} up-to-date. Not updating")
                continue
            else:
                print(f"updating package {package_name} form {arch}")

            remote_package = remote_repository.open(path)
            files = [remote_package]
            try:
                handle_package_files(
                    channel_name,
                    files,
                    dao,
                    auth,
                    force,
                    background_tasks,
                    update_indexes=False,
                )
            except Exception as exc:
                # LOG: could not process package {package_name}
                # from channel {channel_name} due to error
                # {exc}
                if not skip_errors:
                    raise exc
    indexing.update_indexes(dao, pkgstore, channel_name)


def synchronize_packages(
    new_channel,
    dao,
    pkgstore,
    auth,
    session,
    background_tasks,
):

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
        background_tasks.add_task(
            initial_sync_mirror,
            new_channel.name,
            remote_repo,
            arch,
            dao,
            pkgstore,
            auth,
            background_tasks,
        )
