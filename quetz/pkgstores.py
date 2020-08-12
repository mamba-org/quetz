# Copyright 2020 Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import abc
import contextlib
import os.path as path
import shutil

import fsspec
try:
    import s3fs
except ModuleNotFoundError:
    s3fs = None

from quetz.errors import ConfigError


class PackageStore(abc.ABC):
    @abc.abstractmethod
    def __init__(self, config):
        pass

    @abc.abstractmethod
    def create_channel(self, name):
        pass

    @abc.abstractmethod
    def add_package(self, channel, src, dest):
        pass

    @abc.abstractmethod
    def serve_package(self, channel, package):
        pass

class LocalStore(PackageStore):
    def __init__(self, config):
        self.fs = fsspec.filesystem("file")
        self.channels_dir = config['channels_dir']

    def create_channel(self, name):
        self.fs.makedirs(path.join(self.channels_dir, name), exist_ok=True)

    def add_package(self, channel, src, dest):
        full_path = path.join(self.channels_dir, channel, dest)
        self.fs.makedirs(path.dirname(full_path), exist_ok=True)

        with self.fs.open(full_path, "wb") as pkg:
            shutil.copyfileobj(src, pkg)

    def serve_package(self, channel, package):
        return self.fs.open(path.join(self.channels_dir, channel, package)).f


class S3Store(PackageStore):
    def __init__(self, config):
        if not s3fs:
            raise ModuleNotFoundError("S3 package store requires s3fs module")

        client_kwargs = {}
        url = config.get('url')
        if url:
            client_kwargs['endpoint_url'] = url

        self.fs = s3fs.S3FileSystem(
            key=config['key'], secret=config['secret'],
            client_kwargs=client_kwargs)

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
        with self._get_fs() as fs:
            try:
                fs.mkdir(self._bucket_map(name))
            except FileExistsError:
                pass

    def add_package(self, channel, src, dest):
        with self._get_fs() as fs:
            bucket = self._bucket_map(channel)
            with fs.open(path.join(bucket, dest), "wb") as pkg:
                shutil.copyfileobj(src, pkg)

    def serve_package(self, channel, package):
        with self._get_fs() as fs:
            return fs.open(
                path.join(self._bucket_map(channel), package))
