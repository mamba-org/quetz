from quetz import db_models
from fastapi import Depends
from fastapi.responses import StreamingResponse, FileResponse
from quetz.main import get_channel_allow_mirror

import os
import requests


class RemoteRepository:
    """Ressource object for external package repositories."""

    def __init__(self, channel: db_models.Channel = Depends(get_channel_allow_mirror)):
        self.host = channel.mirror_channel_url
        self.chunk_size = 10000

    def open(self, path):
        remote_url = os.path.join(self.host, path)
        response = requests.get(remote_url, stream=True)
        for chunk in response.iter_content(chunk_size=self.chunk_size):
            yield chunk


def get_from_cache_or_download(
    repository, cache, target, exclude=["repodata.json", "current_respodata.json"]
):
    """Serve from cache or download if missing."""

    _, filename = os.path.split(target)
    skip_cache = filename in exclude

    if skip_cache:
        data_stream = repository.open(target)
        return StreamingResponse(data_stream)

    if target not in cache:
        # copy from repository to cache
        data_stream = repository.open(target)
        cache.dump(target, data_stream)

    return FileResponse(cache[target])


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
            for chunk in stream:
                fid.write(chunk)

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
