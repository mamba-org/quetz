# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import os
from enum import Enum
from secrets import token_bytes
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    NamedTuple,
    NoReturn,
    Optional,
    Type,
    Union,
)

from pydantic import BaseModel, SecretStr, validator

import appdirs
import pluggy
import toml

from quetz import hooks, pkgstores
from quetz.db_models import Base
from quetz.errors import ConfigError

_filename = "config.toml"
_env_prefix = "QUETZ_"
_env_config_file = "CONFIG_FILE"
_site_dir = appdirs.site_config_dir("quetz")
_user_dir = appdirs.user_config_dir("quetz")

PAGINATION_LIMIT = 20


class LogLevel(str, Enum):
    critical = "critical"
    error = "error"
    warning = "warning"
    info = "info"
    debug = "debug"
    trace = "trace"


class AuthModel(BaseModel):
    authenticators: List[str] = []


class SQLAlchemyModel(BaseModel):
    database_url: str = "sqlite:///./quetz.sqlite"
    database_plugin_path = ''
    echo_sql: bool = False


class UserModel(BaseModel):
    admins: List[str] = []
    maintainers: List[str] = []
    members: List[str] = []
    default_role: str = None
    create_default_channel: bool = False


class SessionModel(BaseModel):
    secret: SecretStr = token_bytes(32).hex()
    https_only: bool = True


class LocalStoreModel(BaseModel):
    redirect_enabled: bool = False
    redirect_endpoint = '/files'


class General(BaseModel):
    package_unpack_threads: int = 1
    frontend_dir = ''


class Cors(BaseModel):
    allow_origins: List[str] = []
    allow_credentials: bool = True
    allow_methods: List[str] = ["*"]
    allow_headers: List[str] = ["*"]


class S3Model(BaseModel):
    access_key = ''
    secret_key = ''
    url = ''
    region = ''
    bucket_prefix = ''
    bucket_suffix = ''


class AzureBlobModel(BaseModel):
    account_name = ''
    account_access_key = ''
    conn_str = ''
    container_prefix = ''
    container_suffix = ''


class LoggingModel(BaseModel):
    level: LogLevel = "info"
    file: str = None

    class Config:
        anystr_lower = True
        validate_all = True
        use_enum_values = True

    @validator('level', pre=True)
    def lower_case(cls, v):
        return v.lower()


class UserModel(BaseModel):
    admins: List[str] = []
    maintainers: List[str] = []
    members: List[str] = []
    default_role: str = None
    create_default_channel: bool = False


class RedisModel(BaseModel):
    ip = '127.0.0.1'
    port: int = 6379
    db: int = 0


class WorkerModel(BaseModel):
    type = 'thread'
    redis: RedisModel = RedisModel()


class PluginsModel(BaseModel):
    enabled: List[str] = []


class MirroringModel(BaseModel):
    batch_length: int = 10
    batch_size: int = int(1e8)
    num_parallel_downloads: int = 10


class QuotasModel(BaseModel):
    channel_quota: bool = False


class PluginModel(BaseModel):
    plugins_required: List[str] = []


class QuetzModel(PluginModel):
    auth = AuthModel()
    users = UserModel()
    session = SessionModel()
    sqlalchemy = SQLAlchemyModel()
    local_store: LocalStoreModel = LocalStoreModel()
    logging: LoggingModel = LoggingModel()
    worker: WorkerModel = WorkerModel()
    mirroring: MirroringModel = MirroringModel()
    quotas: QuotasModel = QuotasModel()

    def get_package_store(self) -> pkgstores.PackageStore:
        """Return the appropriate package store as set in the config.

        Returns
        -------
        package_store : pkgstores.PackageStore
            The package store instance to enact package operations against
        """
        if self.configured_section('s3'):
            return pkgstores.S3Store(
                {
                    'key': self.s3_access_key,
                    'secret': self.s3_secret_key,
                    'url': self.s3_url,
                    'region': self.s3_region,
                    'bucket_prefix': self.s3_bucket_prefix,
                    'bucket_suffix': self.s3_bucket_suffix,
                }
            )
        elif self.configured_section('azure_blob'):
            return pkgstores.AzureBlobStore(
                {
                    'account_name': self.azure_blob_account_name,
                    'account_access_key': self.azure_blob_account_access_key,
                    'conn_str': self.azure_blob_conn_str,
                    'container_prefix': self.azure_blob_container_prefix,
                    'container_suffix': self.azure_blob_container_suffix,
                }
            )
        elif self.config.get('gcs'):
            return pkgstores.GoogleCloudStorageStore(
                {
                    'project': self.gcs_project,
                    'token': self.gcs_token,
                    'bucket_prefix': self.gcs_bucket_prefix,
                    'bucket_suffix': self.gcs_bucket_suffix,
                }
            )
        else:
            return pkgstores.LocalStore(
                {
                    'channels_dir': 'channels',
                    'redirect_enabled': self.local_store_redirect_enabled,
                    'redirect_endpoint': self.local_store_redirect_endpoint,
                    'redirect_secret': self.local_store_redirect_secret,
                    'redirect_expiration': int(self.local_store_redirect_expiration),
                }
            )

    def configured_section(self, section: str) -> bool:
        """Return if a given section has been configured.

        Parameters
        ----------
        provider: str
            The section name in config

        Returns
        -------
        bool
            Wether or not the given section is configured
        """

        return section in self.__fields_set__


def find_config_files(config_file: str = None):
    env_var_dir = os.getenv(f"{_env_prefix}{_env_config_file}")
    config_dirs = [_user_dir, _site_dir]
    config_files = [config_file, env_var_dir] + [
        os.path.join(d, _filename) for d in config_dirs
    ]

    for f in config_files:
        if f and os.path.isfile(f):
            return f

    raise ValueError("No config file found from various sources")


def read_config_file(config_file: str = None):
    path = os.path.abspath(config_file)

    with open(path) as f:
        try:
            return dict(toml.load(f)), path
        except toml.TomlDecodeError as e:
            raise ConfigError(f"failed to load config file '{path}': {e}")


class Config:

    _config_dirs = [_site_dir, _user_dir]
    _config_files = [os.path.join(d, _filename) for d in _config_dirs]

    _root_model = []
    _instances: Dict[(Type[PluginModel], str), PluginModel] = {}
    _obj: dict = None
    _files: Dict[str, dict] = {}

    def __new__(cls, plugin_model: Type[PluginModel], file: str = None):

        if plugin_model not in cls._files or file not in cls._files[plugin_model]:
            config_obj, path = read_config_file(find_config_files(file))

            if plugin_model not in cls._files:
                cls._files[plugin_model] = path
            else:
                cls._files[plugin_model].append(path)

            cls._obj = config_obj

            config = plugin_model.parse_obj(cls._obj)
            cls._instances[plugin_model] = config
            return config

        if plugin_model in cls._instances:
            return cls._instances[plugin_model]

    @classmethod
    def register(cls, plugin_model: Type[PluginModel], file: str = None):

        if file not in cls._files:
            config_obj, _ = read_config_file(find_config_files(file))
            cls._files[file] = config_obj

        if (plugin_model, file) in cls._instances:
            config = plugin_model.parse_obj(config_obj)

            cls._instances[plugin_model] = config

    @classmethod
    @property
    def file(cls):
        return cls._file


def create_config(
    client_id: str = "",
    client_secret: str = "",
    database_url: str = "sqlite:///./quetz.sqlite",
    secret: str = token_bytes(32).hex(),
    https: str = 'true',
) -> str:
    """Create a configuration file from a template.

    Parameters
    ----------
    client_id : str, optional
        The client ID {default=""}
    client_secret : str, optional
        The client secret {default=""}
    database_url : str, optional
        The URL of the database {default="sqlite:///./quetz.sqlite"}
    secret : str, optional
        The secret of the session {default=randomly create}
    https : str, optional
        Whether to use HTTPS, or not {default="true"}

    Returns
    -------
    configuration : str
        The configuration
    """
    with open(os.path.join(os.path.dirname(__file__), _filename), 'r') as f:
        config = ''.join(f.readlines())

    return config.format(client_id, client_secret, database_url, secret, https)


def get_plugin_manager(config=None) -> pluggy.PluginManager:
    """Create an instance of plugin manager."""

    if not config:
        config = Config(QuetzModel)

    pm = pluggy.PluginManager("quetz")
    pm.add_hookspecs(hooks)
    if config.configured_section("plugins"):
        for name in config.plugins_enabled:
            pm.load_setuptools_entrypoints("quetz", name)
    else:
        pm.load_setuptools_entrypoints("quetz")
    return pm
