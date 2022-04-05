# Copyright 2020 Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import abc
import base64
import calendar
import contextlib
import datetime
import hashlib
import logging
import os
import os.path as path
import shutil
import tempfile
from contextlib import contextmanager
from os import PathLike
from threading import Lock
from typing import IO, BinaryIO, List, NoReturn, Tuple, Union

import fsspec
from tenacity import retry, retry_if_exception_type, stop_after_attempt

try:
    import xattr

    has_xattr = True
except ImportError:
    has_xattr = False

from quetz.errors import ConfigError

File = BinaryIO

StrPath = Union[str, PathLike]

logger = logging.getLogger("quetz")


class PackageStore(abc.ABC):
    def __init__(self):
        self._download_locks = {}

    def get_download_lock(self, channel: str, destination: str):
        return self._download_locks.get((channel, destination))

    def create_download_lock(self, channel: str, destination: str):
        lock = self._download_locks[(channel, destination)] = Lock()
        return lock

    def delete_download_lock(self, channel: str, destination: str):
        del self._download_locks[(channel, destination)]

    @property
    def kind(self):
        return type(self).__name__

    @property
    @abc.abstractmethod
    def support_redirect(self) -> bool:
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
    def url(self, channel: str, src: str, expires: int = 0) -> str:
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
    def file_exists(self, channel: str, destination: str):
        """Return True if the file exists"""

    @abc.abstractmethod
    def get_filemetadata(self, channel: str, src: str) -> Tuple[int, int, str]:
        """get file metadata: returns (file size, last modified time, etag)"""

    @abc.abstractclassmethod
    def cleanup_temp_files(self, channel: str, dry_run: bool = False):
        """clean up temporary `*.json{HASH}.[bz2|gz]` files from pkgstore"""


# generate a secret token for use with nginx secure link
# similar to https://stackoverflow.com/a/52764346 (thanks @flix on stackoverflow)
def nginx_secure_link(url: str, secret: str, expires=3600):
    future = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires)
    expire_ts = calendar.timegm(future.timetuple())

    hash_string = f"{expire_ts}{url} {secret}".encode('utf-8')
    m = hashlib.md5(hash_string).digest()

    base64_hash = base64.urlsafe_b64encode(m)
    base64_s = base64_hash.decode('utf-8').rstrip('=')
    return base64_s, expire_ts


class LocalStore(PackageStore):
    def __init__(self, config):
        self.fs: fsspec.AbstractFileSystem = fsspec.filesystem("file")
        self.channels_dir = config['channels_dir']
        self.redirect_enabled = config['redirect_enabled']
        self.redirect_endpoint = config['redirect_endpoint']
        self.redirect_secret = config.get('redirect_secret')
        self.redirect_expiration = config.get('redirect_expiration')

        super().__init__()

    @property
    def support_redirect(self):
        return self.redirect_enabled

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

    def file_exists(self, channel: str, destination: str):
        return self.fs.exists(path.join(self.channels_dir, channel, destination))

    def serve_path(self, channel, src):
        return self.fs.open(path.join(self.channels_dir, channel, src))

    def list_files(self, channel: str):
        channel_dir = os.path.join(self.channels_dir, channel)
        return [os.path.relpath(f, channel_dir) for f in self.fs.find(channel_dir)]

    def url(self, channel: str, src: str, expires=0):
        if self.redirect_enabled:
            # generate url + secret if necessary
            if self.redirect_secret:
                url = path.join(self.channels_dir, channel, src)
                md5hash, expires_by = nginx_secure_link(
                    url, self.redirect_secret, self.redirect_expiration
                )
                return (
                    path.join(self.redirect_endpoint, url)
                    + f"?md5={md5hash}&expires={expires_by}"
                )

            return path.join(self.redirect_endpoint, self.channels_dir, channel, src)
        else:
            return path.abspath(path.join(self.channels_dir, channel, src))

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

    def cleanup_temp_files(self, channel: str, dry_run: bool = False):
        temp_files = []
        for each_end in [".bz2", ".gz"]:
            temp_files.extend(
                self.fs.glob(
                    f"{path.join(self.channels_dir, channel)}/**/*.json?*{each_end}"
                )
            )

        for each_temp_file in temp_files:
            logger.info(f"removing {each_temp_file} from pkgstore")
            if not dry_run:
                self.fs.delete(each_temp_file)


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
        super().__init__()

    @property
    def support_redirect(self):
        return True

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

    def file_exists(self, channel: str, destination: str):
        channel_bucket = self._bucket_map(channel)
        with self._get_fs() as fs:
            return fs.exists(path.join(channel_bucket, destination))

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

    def cleanup_temp_files(self, channel: str, dry_run: bool = False):
        with self._get_fs() as fs:
            temp_files = []
            for each_end in [".bz2", ".gz"]:
                temp_files.extend(
                    fs.glob(f"{self._bucket_map(channel)}/**/*.json?*{each_end}")
                )

            for each_temp_file in temp_files:
                logger.info(f"removing {each_temp_file} from pkgstore")
                if not dry_run:
                    fs.delete(each_temp_file)


class AzureBlobStore(PackageStore):
    def __init__(self, config):
        try:
            import adlfs
        except ModuleNotFoundError:
            raise ModuleNotFoundError("Azure Blob package store requires adlfs module")

        self.storage_account_name = config.get('account_name')
        self.access_key = config.get("account_access_key")
        self.conn_string = config.get("conn_str")

        self.fs = adlfs.AzureBlobFileSystem(
            account_name=self.storage_account_name,
            connection_string=self.conn_string,
            account_key=self.access_key,
        )

        self.container_prefix = config['container_prefix']
        self.container_suffix = config['container_suffix']
        super().__init__()

    @property
    def support_redirect(self):
        return True

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

    def file_exists(self, channel: str, destination: str):
        channel_container = self._container_map(channel)
        with self._get_fs() as fs:
            return fs.exists(path.join(channel_container, destination))

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
        with self._get_fs() as fs:
            return fs.url(path.join(self._container_map(channel), src), expires)

    def get_filemetadata(self, channel: str, src: str):
        with self._get_fs() as fs:
            filepath = path.join(self._container_map(channel), src)
            infodata = fs.info(filepath)

            mtime = infodata['last_modified'].timestamp()
            msize = infodata['size']
            etag = infodata['etag']

            return (msize, mtime, etag)

    def cleanup_temp_files(self, channel: str, dry_run: bool = False):
        with self._get_fs() as fs:
            temp_files = []
            for each_end in [".bz2", ".gz"]:
                temp_files.extend(
                    fs.glob(f"{self._container_map(channel)}/**/*.json?*{each_end}")
                )

            for each_temp_file in temp_files:
                logger.info(f"removing {each_temp_file} from pkgstore")
                if not dry_run:
                    fs.delete(each_temp_file)


class GoogleCloudStorageStore(PackageStore):
    def __init__(self, config):
        try:
            import gcsfs
        except ModuleNotFoundError:
            raise ModuleNotFoundError(
                "Google Cloud Storage package store requires gcsfs module"
            )

        self.project = config.get("project")
        self.token = config.get("token")
        self.cache_timeout = config.get("cache_timeout")
        self.region = config.get("region")

        self.fs = gcsfs.GCSFileSystem(
            project=self.project,
            token=self.token if self.token else None,
            cache_timeout=self.cache_timeout,
            default_location=self.region,
        )

        self.bucket_prefix = config['bucket_prefix']
        self.bucket_suffix = config['bucket_suffix']
        super().__init__()

    @property
    def support_redirect(self):
        # `gcsfs` currently doesnt support signing yet. Once this is implemented we
        # can enable this again.
        return True

    @contextlib.contextmanager
    def _get_fs(self):
        try:
            yield self.fs
        except PermissionError as e:
            raise ConfigError(
                f"{e} - check configured Google Cloud Storage credentials"
            )

    def _bucket_map(self, name):
        return f"{self.bucket_prefix}{name}{self.bucket_suffix}"

    def create_channel(self, name):
        """Create the container if one doesn't already exist

        Parameters
        ----------
        name : str
            The name of the container to create on azure blob
        """
        with self._get_fs() as fs:
            bucket_name = self._bucket_map(name)
            if f"{bucket_name}/" not in fs.buckets:
                fs.mkdir(bucket_name)
                fs.invalidate_cache()

    def remove_channel(self, name):
        channel_path = self._bucket_map(name)
        with self._get_fs() as fs:
            fs.rm(channel_path, recursive=True)

    def add_package(self, package: File, channel: str, destination: str) -> NoReturn:
        with self._get_fs() as fs:
            container = self._bucket_map(channel)
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
            container = self._bucket_map(channel)
            with fs.open(path.join(container, destination), mode) as f:
                f.write(data)

    def serve_path(self, channel, src):
        with self._get_fs() as fs:
            file = fs.open(path.join(self._bucket_map(channel), src))
            info = file.info()
            if info["type"] != "file":
                raise FileNotFoundError()
            return file

    def delete_file(self, channel: str, destination: str):
        channel_container = self._bucket_map(channel)

        with self._get_fs() as fs:
            fs.delete(path.join(channel_container, destination))

    def move_file(self, channel: str, source: str, destination: str):
        channel_container = self._bucket_map(channel)

        with self._get_fs() as fs:
            fs.move(
                path.join(channel_container, source),
                path.join(channel_container, destination),
            )

    def file_exists(self, channel: str, destination: str):
        channel_container = self._bucket_map(channel)
        with self._get_fs() as fs:
            return fs.exists(path.join(channel_container, destination))

    def list_files(self, channel: str):
        def remove_prefix(text, prefix):
            if text.startswith(prefix):
                return text[len(prefix) :].lstrip("/")  # noqa: E203
            return text

        channel_container = self._bucket_map(channel)

        with self._get_fs() as fs:
            return [
                remove_prefix(f, channel_container) for f in fs.find(channel_container)
            ]

    def url(self, channel: str, src: str, expires=3600):
        # expires is in seconds, so the default is 60 minutes!
        with self._get_fs() as fs:
            expiration_timestamp = (
                int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())
                + expires
            )
            redirect_url = fs.sign(
                path.join(self._bucket_map(channel), src), expiration_timestamp
            )
            return redirect_url

    def get_filemetadata(self, channel: str, src: str):
        with self._get_fs() as fs:
            filepath = path.join(self._bucket_map(channel), src)
            infodata = fs.info(filepath)

            if infodata['type'] != 'file':
                raise FileNotFoundError()

            mtime = datetime.datetime.fromisoformat(
                infodata['updated'].replace('Z', '+00:00')
            ).timestamp()
            msize = infodata['size']
            etag = infodata['etag']

            return (msize, mtime, etag)

    def cleanup_temp_files(self, channel: str, dry_run: bool = False):
        with self._get_fs() as fs:
            temp_files = []
            for each_end in [".bz2", ".gz"]:
                temp_files.extend(
                    fs.glob(f"{self._bucket_map(channel)}/**/*.json?*{each_end}")
                )

            for each_temp_file in temp_files:
                logger.info(f"removing {each_temp_file} from pkgstore")
                if not dry_run:
                    fs.delete(each_temp_file)
