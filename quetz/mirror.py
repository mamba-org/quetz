from quetz import db_models
from fastapi import Depends
from fastapi.responses import StreamingResponse, FileResponse
from quetz.main import get_channel_or_fail

import os
import requests


class RemoteRepository:
    def __init__(self, channel: db_models.Channel = Depends(get_channel_or_fail)):
        self.host = channel.mirror_channel_url
        self.chunk_size = 10000

    def open(self, path):
        remote_url = os.path.join(self.host, path)
        response = requests.get(remote_url, stream=True)
        for chunk in response.iter_content(chunk_size=self.chunk_size):
            yield chunk


class LocalCache:
    def __init__(self, channel: db_models.Channel = Depends(get_channel_or_fail)):
        self.cache_dir = "cache"
        self.channel = channel.name
        self.exclude = ["repodata.json", "current_repodata.json"]

    def add_and_get(self, repository: RemoteRepository, path: str):
        _, filename = os.path.split(path)
        skip_cache = filename in self.exclude

        if skip_cache:
            data_stream = repository.open(path)
            return StreamingResponse(data_stream)

        cache_path = os.path.join(self.cache_dir, self.channel, path)
        if not os.path.isfile(cache_path):
            data_stream = repository.open(path)
            package_dir, _ = os.path.split(cache_path)
            os.makedirs(package_dir, exist_ok=True)
            with open(cache_path, "wb") as fid:
                for chunk in data_stream:
                    fid.write(chunk)
        return FileResponse(cache_path)
