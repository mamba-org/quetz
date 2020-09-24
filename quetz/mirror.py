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

    force = False

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
    last_timestamp = 0
    last_synchronization = channel.timestamp_mirror_sync
    for package_name, metadata in packages.items():
        path = os.path.join(arch, package_name)
        time_modified = metadata.get("time_modified", 0)
        last_timestamp = max(time_modified, last_timestamp)
        # if there is no modification date (ex. anaconda server) or
        # modification is older than the timestamp of last synchronisation
        # skip uploading file
        if time_modified and time_modified <= last_synchronization:
            continue
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
            # LOG: could not process package {package_name} from channel {channel_name}
            if not skip_errors:
                raise exc
    last_synchronisation = max(last_synchronization, last_timestamp)
    dao.update_channel(channel_name, {"timestamp_mirror_sync": last_synchronisation})
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
