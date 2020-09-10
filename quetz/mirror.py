import os
import shutil
from tempfile import SpooledTemporaryFile

import requests
from fastapi.responses import FileResponse, StreamingResponse


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


class RemoteFile:
    def __init__(self, host: str, path: str, session=None):
        if session is None:
            session = requests.Session()
        remote_url = os.path.join(host, path)
        response = session.get(remote_url, stream=True)
        self.file = SpooledTemporaryFile()
        shutil.copyfileobj(response.raw, self.file)
        # rewind
        self.file.seek(0)
        _, self.filename = os.path.split(remote_url)
        self.content_type = response.headers.get("content-type")


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
