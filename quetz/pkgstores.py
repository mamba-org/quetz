# Copyright 2020 Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import abc
import contextlib
import os
import os.path as path
import shutil
import tempfile
from contextlib import contextmanager
from typing import IO, BinaryIO, List, NoReturn, Union

import fsspec

from quetz.errors import ConfigError

File = BinaryIO


class PackageStore(abc.ABC):
    @abc.abstractmethod
    def __init__(self):
        pass

    @abc.abstractmethod
    def create_channel(self, name):
        pass

    @abc.abstractmethod
    def list_files(self, channel: str) -> List[str]:
        pass

    @abc.abstractmethod
    def add_package(self, package: File, channel: str, destination: str) -> NoReturn:
        pass

    @abc.abstractmethod
    def add_file(
        self, data: Union[str, bytes], channel: str, destination: str
    ) -> NoReturn:
        pass

    @abc.abstractmethod
    def serve_path(self, channel, src):
        pass

    @abc.abstractmethod
    def delete_file(self, channel: str, destination: str):
        """remove file from package store"""


class LocalStore(PackageStore):
    def __init__(self, config):
        self.fs: fsspec.AbstractFileSystem = fsspec.filesystem("file")
        self.channels_dir = config['channels_dir']

    @contextmanager
    def _atomic_open(self, channel: str, destination: str, mode="wb") -> IO:
        full_path = path.join(self.channels_dir, channel, destination)
        self.fs.makedirs(path.dirname(full_path), exist_ok=True)

        # Creates a tempfile in the same directory as the target filename.
        # Renames it into place when it's closed.
        fh, tmpname = tempfile.mkstemp(dir=os.path.dirname(full_path), prefix=".")
        f = open(fh, mode)
        try:
            yield f
        except:  # noqa
            f.close()
            os.remove(tmpname)
            raise
        else:
            f.flush()  # Belt and braces (network file systems)
            f.close()
            os.rename(tmpname, full_path)

    def create_channel(self, name):
        self.fs.makedirs(path.join(self.channels_dir, name), exist_ok=True)

    def add_package(self, package: File, channel: str, destination: str) -> NoReturn:

        with self._atomic_open(channel, destination) as f:
            shutil.copyfileobj(package, f)

    def add_file(
        self, data: Union[str, bytes], channel: str, destination: str
    ) -> NoReturn:

        mode = "w" if isinstance(data, str) else "wb"
        with self._atomic_open(channel, destination, mode) as f:
            f.write(data)

    def delete_file(self, channel: str, destination: str):
        self.fs.delete(path.join(self.channels_dir, channel, destination))

    def serve_path(self, channel, src):
        return self.fs.open(path.join(self.channels_dir, channel, src)).f

    def list_files(self, channel: str):
        channel_dir = os.path.join(self.channels_dir, channel)
        return [os.path.relpath(f, channel_dir) for f in self.fs.find(channel_dir)]


class S3Store(PackageStore):
    def __init__(self, config):
        try:
            import s3fs
        except ModuleNotFoundError:
            raise ModuleNotFoundError("S3 package store requires s3fs module")

        client_kwargs = {}
        url = config.get('url')
        region = config.get("region")
        if url:
            client_kwargs['endpoint_url'] = url
        if region:
            client_kwargs["region_name"] = region

        # When using IAM, key and secret will be empty, so need to pass None
        # to the s3fs constructor
        key = config['key'] if config['key'] != '' else None
        secret = config['secret'] if config['secret'] != '' else None
        self.fs = s3fs.S3FileSystem(key=key, secret=secret, client_kwargs=client_kwargs)

        self.bucket_prefix = config['bucket_prefix']
        self.bucket_suffix = config['bucket_suffix']

    @contextlib.contextmanager
    def _get_fs(self):
        try:
            yield self.fs
        except PermissionError as e:
            raise ConfigError(f"{e} - check configured S3 credentials")

    def _bucket_map(self, name):
        return f"{self.bucket_prefix}{name}{self.bucket_suffix}"

    def create_channel(self, name):
        """Create the bucket if one doesn't already exist

        Parameters
        ----------
        name : str
            The name of the bucket to create on s3
        """
        with self._get_fs() as fs:
            try:
                fs.mkdir(self._bucket_map(name), acl="private")
            except FileExistsError:
                pass

    def add_package(self, package: File, channel: str, destination: str) -> NoReturn:
        with self._get_fs() as fs:
            bucket = self._bucket_map(channel)
            with fs.transaction:
                with fs.open(
                    path.join(bucket, destination), "wb", acl="private"
                ) as pkg:
                    shutil.copyfileobj(package, pkg)

    def add_file(
        self, data: Union[str, bytes], channel: str, destination: str
    ) -> NoReturn:
        if type(data) is str:
            mode = "w"
        else:
            mode = "wb"

        with self._get_fs() as fs:
            bucket = self._bucket_map(channel)
            with fs.transaction:
                with fs.open(path.join(bucket, destination), mode, acl="private") as f:
                    f.write(data)

    def serve_path(self, channel, src):
        with self._get_fs() as fs:
            return fs.open(path.join(self._bucket_map(channel), src))

    def list_files(self, channel: str):
        def remove_prefix(text, prefix):
            if text.startswith(prefix):
                return text[len(prefix) :].lstrip("/")  # noqa: E203
            return text

        channel_bucket = self._bucket_map(channel)

        return [remove_prefix(f, channel_bucket) for f in self.fs.find(channel_bucket)]
