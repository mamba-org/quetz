# Copyright 2020 Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import abc
import contextlib
import hashlib
import os
import os.path as path
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from os import PathLike
from typing import IO, BinaryIO, List, NoReturn, Tuple, Union

import fsspec
from tenacity import retry, retry_if_exception_type, stop_after_attempt

try:
    import xattr

    has_xattr = True
except ImportError:
    has_xattr = False

try:
    import azure.storage.blob as azure

    azure_available = True
except ImportError:
    azure_available = False

from quetz.errors import ConfigError

File = BinaryIO

StrPath = Union[str, PathLike]


class PackageStore(abc.ABC):
    @abc.abstractmethod
    def __init__(self):
        pass

    @abc.abstractmethod
    def create_channel(self, name):
        pass

    @abc.abstractmethod
    def remove_channel(self, name):
        """remove channel recursively"""
        pass

    @abc.abstractmethod
    def list_files(self, channel: str) -> List[str]:
        pass

    @abc.abstractmethod
    def add_package(self, package: File, channel: str, destination: str) -> NoReturn:
        pass

    @abc.abstractmethod
    def add_file(
        self, data: Union[str, bytes], channel: str, destination: StrPath
    ) -> NoReturn:
        pass

    @abc.abstractmethod
    def serve_path(self, channel, src):
        pass

    @abc.abstractmethod
    def delete_file(self, channel: str, destination: str):
        """remove file from package store"""

    @abc.abstractmethod
    def move_file(self, channel: str, source: str, destination: str):
        """move file from source to destination in package store"""

    @abc.abstractmethod
    def get_filemetadata(self, channel: str, src: str) -> Tuple[int, int, str]:
        """get file metadata: returns (file size, last modified time, etag)"""


class LocalStore(PackageStore):
    def __init__(self, config):
        self.fs: fsspec.AbstractFileSystem = fsspec.filesystem("file")
        self.channels_dir = config['channels_dir']

    @contextmanager
    def _atomic_open(self, channel: str, destination: StrPath, mode="wb") -> IO:
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

    def remove_channel(self, name):
        channel_path = path.join(self.channels_dir, name)
        self.fs.rm(channel_path, recursive=True)

    def add_package(self, package: File, channel: str, destination: str) -> NoReturn:

        with self._atomic_open(channel, destination) as f:
            shutil.copyfileobj(package, f)

    def add_file(
        self, data: Union[str, bytes], channel: str, destination: StrPath
    ) -> NoReturn:

        mode = "w" if isinstance(data, str) else "wb"
        with self._atomic_open(channel, destination, mode) as f:
            f.write(data)

    def delete_file(self, channel: str, destination: str):
        self.fs.delete(path.join(self.channels_dir, channel, destination))

    def move_file(self, channel: str, source: str, destination: str):
        self.fs.move(
            path.join(self.channels_dir, channel, source),
            path.join(self.channels_dir, channel, destination),
        )

    def serve_path(self, channel, src):
        return self.fs.open(path.join(self.channels_dir, channel, src)).f

    def list_files(self, channel: str):
        channel_dir = os.path.join(self.channels_dir, channel)
        return [os.path.relpath(f, channel_dir) for f in self.fs.find(channel_dir)]

    def get_filemetadata(self, channel: str, src: str):
        filepath = path.abspath(path.join(self.channels_dir, channel, src))
        if not path.exists(filepath):
            raise FileNotFoundError()

        stat_res = os.stat(filepath)
        mtime = stat_res.st_mtime
        msize = stat_res.st_size

        xattr_failed = False
        if has_xattr:
            try:
                # xattr will fail here if executing on e.g. the tmp filesystem
                attrs = xattr.xattr(filepath)
                attrs['user.testifpermissionok'] = b''
                try:
                    etag = attrs['user.etag'].decode('ascii')
                except KeyError:
                    # calculate md5 sum
                    with self.fs.open(filepath, 'rb') as f:
                        etag = hashlib.md5(f.read()).hexdigest()
                    attrs['user.etag'] = etag.encode('ascii')
            except OSError:
                xattr_failed = True

        if not has_xattr or xattr_failed:
            etag_base = str(mtime) + "-" + str(msize)
            etag = hashlib.md5(etag_base.encode()).hexdigest()

        return (msize, mtime, etag)


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

    # we need to retry due to eventual (vs strong) consistency on Openstack Swift
    @retry(stop=stop_after_attempt(5), retry=retry_if_exception_type(OSError))
    def remove_channel(self, name):
        channel_path = self._bucket_map(name)
        self.fs.rm(channel_path, recursive=True, acl="private")

    def add_package(self, package: File, channel: str, destination: str) -> NoReturn:
        with self._get_fs() as fs:
            bucket = self._bucket_map(channel)
            with fs.open(path.join(bucket, destination), "wb", acl="private") as pkg:
                # use a chunk size of 10 Megabytes
                shutil.copyfileobj(package, pkg, 10 * 1024 * 1024)

    def add_file(
        self, data: Union[str, bytes], channel: str, destination: StrPath
    ) -> NoReturn:
        if type(data) is str:
            mode = "w"
        else:
            mode = "wb"

        with self._get_fs() as fs:
            bucket = self._bucket_map(channel)
            with fs.open(path.join(bucket, destination), mode, acl="private") as f:
                f.write(data)

    def serve_path(self, channel, src):
        with self._get_fs() as fs:
            return fs.open(path.join(self._bucket_map(channel), src))

    def delete_file(self, channel: str, destination: str):
        channel_bucket = self._bucket_map(channel)

        with self._get_fs() as fs:
            fs.delete(path.join(channel_bucket, destination))

    def move_file(self, channel: str, source: str, destination: str):
        channel_bucket = self._bucket_map(channel)

        with self._get_fs() as fs:
            fs.move(
                path.join(channel_bucket, source),
                path.join(channel_bucket, destination),
            )

    def list_files(self, channel: str):
        def remove_prefix(text, prefix):
            if text.startswith(prefix):
                return text[len(prefix) :].lstrip("/")  # noqa: E203
            return text

        channel_bucket = self._bucket_map(channel)

        with self._get_fs() as fs:
            return [remove_prefix(f, channel_bucket) for f in fs.find(channel_bucket)]

    def url(self, channel: str, src: str, expires=3600):
        # expires is in seconds, so the default is 60 minutes!
        with self._get_fs() as fs:
            return fs.url(path.join(self._bucket_map(channel), src), expires)

    def get_filemetadata(self, channel: str, src: str):
        with self._get_fs() as fs:
            filepath = path.join(self._bucket_map(channel), src)
            infodata = fs.info(filepath)

            mtime = infodata['LastModified'].timestamp()
            msize = infodata['Size']
            etag = infodata['ETag']

            return (msize, mtime, etag)


class AzureBlobStore(PackageStore):
    def __init__(self, config):
        try:
            import adlfs
        except ModuleNotFoundError:
            raise ModuleNotFoundError("Azure Blob package store requires adlfs module")
        if not azure_available:
            raise ModuleNotFoundError(
                "Azure Blob package store requires azure-storage-blob module"
            )

        self.storage_account_name = config.get('account_name')
        self.access_key = config.get("account_access_key")
        self.conn_string = config.get("conn_str")

        self.fs = adlfs.AzureBlobFileSystem(
            account_name=self.storage_account_name, connection_string=self.conn_string
        )

        self.container_prefix = config['container_prefix']
        self.container_suffix = config['container_suffix']

    @contextlib.contextmanager
    def _get_fs(self):
        try:
            yield self.fs
        except PermissionError as e:
            raise ConfigError(f"{e} - check configured Azure Blob credentials")

    def _container_map(self, name):
        return f"{self.container_prefix}{name}{self.container_suffix}"

    def create_channel(self, name):
        """Create the container if one doesn't already exist

        Parameters
        ----------
        name : str
            The name of the container to create on azure blob
        """
        with self._get_fs() as fs:
            try:
                fs.mkdir(self._container_map(name))
            except FileExistsError:
                pass

    def remove_channel(self, name):
        channel_path = self._container_map(name)
        with self._get_fs() as fs:
            fs.rm(channel_path, recursive=True)

    def add_package(self, package: File, channel: str, destination: str) -> NoReturn:
        with self._get_fs() as fs:
            container = self._container_map(channel)
            with fs.open(path.join(container, destination), "wb") as pkg:
                # use a chunk size of 10 Megabytes
                shutil.copyfileobj(package, pkg, 10 * 1024 * 1024)

    def add_file(
        self, data: Union[str, bytes], channel: str, destination: StrPath
    ) -> NoReturn:
        if type(data) is str:
            mode = "w"
        else:
            mode = "wb"

        with self._get_fs() as fs:
            container = self._container_map(channel)
            with fs.open(path.join(container, destination), mode) as f:
                f.write(data)

    def serve_path(self, channel, src):
        with self._get_fs() as fs:
            return fs.open(path.join(self._container_map(channel), src))

    def delete_file(self, channel: str, destination: str):
        channel_container = self._container_map(channel)

        with self._get_fs() as fs:
            fs.delete(path.join(channel_container, destination))

    def move_file(self, channel: str, source: str, destination: str):
        channel_container = self._container_map(channel)

        with self._get_fs() as fs:
            fs.move(
                path.join(channel_container, source),
                path.join(channel_container, destination),
            )

    def list_files(self, channel: str):
        def remove_prefix(text, prefix):
            if text.startswith(prefix):
                return text[len(prefix) :].lstrip("/")  # noqa: E203
            return text

        channel_container = self._container_map(channel)

        with self._get_fs() as fs:
            return [
                remove_prefix(f, channel_container) for f in fs.find(channel_container)
            ]

    def url(self, channel: str, src: str, expires=3600):
        # expires is in seconds, so the default is 60 minutes!
        channel_container = self._container_map(channel)
        sas_token = azure.generate_blob_sas(
            account_name=self.storage_account_name,
            container_name=channel_container,
            blob_name=src,
            account_key=self.access_key,
            permission=azure.BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(seconds=expires),
        )

        bsc = azure.BlobServiceClient.from_connection_string(self.conn_string)
        blob = bsc.get_blob_client(channel_container, src)
        return azure.BlobClient.from_blob_url(blob.url, credential=sas_token).url

    def get_filemetadata(self, channel: str, src: str):
        channel_container = self._container_map(channel)
        bsc = azure.BlobServiceClient.from_connection_string(self.conn_string)
        blob = bsc.get_blob_client(channel_container, src)
        infodata = blob.get_blob_properties()

        mtime = infodata['last_modified'].timestamp()
        msize = infodata['size']
        etag = infodata['etag']

        return (msize, mtime, etag)
