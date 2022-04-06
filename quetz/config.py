# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import logging
import logging.config
import os
from distutils.util import strtobool
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

import appdirs
import pluggy
import toml

from quetz import hooks, pkgstores
from quetz.errors import ConfigError

_filename = "config.toml"
_env_prefix = "QUETZ_"
_env_config_file = "CONFIG_FILE"
_site_dir = appdirs.site_config_dir("quetz")
_user_dir = appdirs.user_config_dir("quetz")

PAGINATION_LIMIT = 20


class ConfigEntry(NamedTuple):
    name: str
    cast: Type
    default: Any = None
    required: bool = True

    def full_name(self, section=""):
        if section:
            section += "_"
        return f"{section}{self.name}"

    def env_var(self, section=""):
        return f"{_env_prefix}{self.full_name(section).upper()}"

    def casted(self, value):
        if self.cast is bool:
            try:
                value = strtobool(str(value))
            except ValueError as e:
                raise ConfigError(f"{self.name}: {e}")

        return self.cast(value)


class ConfigSection(NamedTuple):
    name: str
    entries: List[ConfigEntry]
    required: bool = True


class Config:

    _config_map = [
        ConfigSection(
            "general",
            [
                ConfigEntry("package_unpack_threads", int, 1),
                ConfigEntry("frontend_dir", str, default=""),
                ConfigEntry("redirect_http_to_https", bool, False),
            ],
        ),
        ConfigSection(
            "cors",
            [
                ConfigEntry("allow_origins", list, []),
                ConfigEntry("allow_credentials", bool, True),
                ConfigEntry("allow_methods", bool, ["*"]),
                ConfigEntry("allow_headers", bool, ["*"]),
            ],
            required=False,
        ),
        ConfigSection(
            "github",
            [
                ConfigEntry("client_id", str),
                ConfigEntry("client_secret", str),
            ],
            required=False,
        ),
        ConfigSection(
            "gitlab",
            [
                ConfigEntry("url", str, default="https://gitlab.com"),
                ConfigEntry("client_id", str),
                ConfigEntry("client_secret", str),
            ],
            required=False,
        ),
        ConfigSection(
            "azuread",
            [
                ConfigEntry("client_id", str),
                ConfigEntry("client_secret", str),
                ConfigEntry("tenant_id", str),
            ],
            required=False,
        ),
        ConfigSection(
            "sqlalchemy",
            [
                ConfigEntry("database_url", str),
                ConfigEntry("database_plugin_path", str, default="", required=False),
                ConfigEntry("echo_sql", bool, default=False, required=False),
            ],
        ),
        ConfigSection(
            "session",
            [ConfigEntry("secret", str), ConfigEntry("https_only", bool, default=True)],
        ),
        ConfigSection(
            "local_store",
            [
                ConfigEntry("redirect_enabled", bool, default=False),
                ConfigEntry("redirect_endpoint", str, default="/files"),
                ConfigEntry("redirect_secret", str, default=""),
                ConfigEntry("redirect_expiration", int, default="3600"),
            ],
        ),
        ConfigSection(
            "s3",
            [
                ConfigEntry("access_key", str, default=""),
                ConfigEntry("secret_key", str, default=""),
                ConfigEntry("url", str, default=""),
                ConfigEntry("region", str, default=""),
                ConfigEntry("bucket_prefix", str, default=""),
                ConfigEntry("bucket_suffix", str, default=""),
            ],
            required=False,
        ),
        ConfigSection(
            "azure_blob",
            [
                ConfigEntry("account_name", str, default=""),
                ConfigEntry("account_access_key", str, default=""),
                ConfigEntry("conn_str", str, default=""),
                ConfigEntry("container_prefix", str, default=""),
                ConfigEntry("container_suffix", str, default=""),
            ],
            required=False,
        ),
        ConfigSection(
            "gcs",
            [
                ConfigEntry("project", str, default=""),
                ConfigEntry("token", str, default=""),
                ConfigEntry("bucket_prefix", str, default=""),
                ConfigEntry("bucket_suffix", str, default=""),
                ConfigEntry("cache_timeout", int, default=None),
                ConfigEntry("region", str, default=None),
            ],
            required=False,
        ),
        ConfigSection(
            "google",
            [ConfigEntry("client_id", str), ConfigEntry("client_secret", str)],
            required=False,
        ),
        ConfigSection(
            "logging",
            [
                ConfigEntry("level", str, default="INFO"),
                ConfigEntry("file", str, default=""),
            ],
            required=False,
        ),
        ConfigSection(
            "users",
            [
                ConfigEntry("admins", list, default=list),
                ConfigEntry("maintainers", list, default=list),
                ConfigEntry("members", list, default=list),
                ConfigEntry("default_role", str, required=False),
                ConfigEntry("collect_emails", bool, default=False, required=False),
                ConfigEntry(
                    "create_default_channel", bool, default=False, required=False
                ),
            ],
            required=False,
        ),
        ConfigSection(
            "worker",
            [
                ConfigEntry("type", str, default="thread"),
                ConfigEntry("redis_ip", str, default="127.0.0.1"),
                ConfigEntry("redis_port", int, default=6379),
                ConfigEntry("redis_db", int, default=0),
            ],
            required=False,
        ),
        ConfigSection(
            "plugins",
            [
                ConfigEntry("enabled", list, default=list),
            ],
        ),
        ConfigSection(
            "mirroring",
            [
                ConfigEntry("batch_length", int, default=10),
                ConfigEntry("batch_size", int, default=int(1e8)),
                ConfigEntry("num_parallel_downloads", int, default=int(10)),
            ],
        ),
        ConfigSection(
            "quotas",
            [
                ConfigEntry("channel_quota", int, required=False),
            ],
            required=False,
        ),
    ]
    _config_dirs = [_site_dir, _user_dir]
    _config_files = [os.path.join(d, _filename) for d in _config_dirs]

    _instances: Dict[Optional[str], "Config"] = {}

    def __new__(cls, deployment_config: str = None):
        if not deployment_config and None in cls._instances:
            return cls._instances[None]
        try:
            path = os.path.abspath(cls.find_file(deployment_config))
        except TypeError:
            raise ValueError(
                "Environment Variable QUETZ_CONFIG_FILE \
                 should be set to name / path of the config file"
            )
        if path not in cls._instances:
            config = super().__new__(cls)
            config.init(path)
            cls._instances[path] = config
            # optimization - for default config path we also store the instance
            # under None key
            if not deployment_config:
                cls._instances[None] = config
        return cls._instances[path]

    def __getattr__(self, name: str) -> Any:
        super().__getattr__(self, name)

    @classmethod
    def find_file(cls, deployment_config: str = None):
        config_file_env = os.getenv(f"{_env_prefix}{_env_config_file}")

        deployment_config_files = []
        for f in (deployment_config, config_file_env):
            if f and os.path.isfile(f):
                deployment_config_files.append(f)

        # In order, get configuration from:
        # _site_dir, _user_dir, deployment_config, config_file_env
        for f in cls._config_files + deployment_config_files:
            if os.path.isfile(f):
                return f

    def init(self, path: str) -> NoReturn:
        """Load configurations from various places.

        Order of importance for configuration is:
        host < user profile < deployment < configuration file from env var < value from
        env var

        Parameters
        ----------
        deployment_config : str, optional
            The configuration stored at deployment level
        """

        self.config: Dict[str, Any] = {}

        self.config.update(self._read_config(path))

        self._trigger_update_config()

    def _trigger_update_config(self):
        def set_entry_attr(entry, section=""):
            env_var_value = os.getenv(entry.env_var(section))

            # Override the configuration files if an env variable is defined for
            # the entry.
            if env_var_value:
                value = entry.casted(env_var_value)
            else:
                value = self._get_value(entry, section)

            setattr(self, entry.full_name(section), value)

        for item in self._config_map:
            if isinstance(item, ConfigSection) and (
                item.required or item.name in self.config
            ):
                for entry in item.entries:
                    set_entry_attr(entry, item.name)
            elif isinstance(item, ConfigEntry):
                set_entry_attr(item)

    def _get_value(
        self, entry: ConfigEntry, section: str = ""
    ) -> Union[str, bool, None]:
        """Get an entry value from a configuration mapping.

        Parameters
        ----------
        entry : ConfigEntry
            The entry to search
        section : str
            The section the entry belongs to

        Returns
        -------
        value : Union[str, bool]
            The entry value
        """
        try:
            if section:
                value = self.config[section][entry.name]
            else:
                value = self.config[entry.name]

            return entry.casted(value)

        except KeyError:
            if entry.default is not None:
                if callable(entry.default):
                    return entry.default()
                return entry.default

        msg = f"'{entry.name}' unset but no default specified"
        if section:
            msg += f" for section '{section}'"

        if entry.required:
            raise ConfigError(msg)

        return None

    def _read_config(self, filename: str) -> Dict[str, Any]:
        """Read a configuration file from its path.

        Parameters
        ----------
        filename : str
            The path of the configuration file

        Returns
        -------
        configuration : Dict[str, str]
            The mapping of configuration variables found in the file
        """
        with open(filename) as f:
            try:
                return dict(toml.load(f))
            except toml.TomlDecodeError as e:
                raise ConfigError(f"failed to load config file '{filename}': {e}")

    def get_package_store(self) -> pkgstores.PackageStore:
        """Return the appropriate package store as set in the config.

        Returns
        -------
        package_store : pkgstores.PackageStore
            The package store instance to enact package operations against
        """
        if self.config.get('s3'):
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
        elif self.config.get('azure_blob'):
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
                    'cache_timeout': self.gcs_cache_timeout,
                    'region': self.region,
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

        return bool(self.config.get(section))

    def register(self, extra_config: Iterable[ConfigSection]):
        """Register additional config variables"""
        self._config_map += extra_config
        self._trigger_update_config()


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


def colourized_formatter(fmt="", use_colors=True):
    try:
        from uvicorn.logging import ColourizedFormatter

        return ColourizedFormatter(fmt, use_colors=use_colors)
    except ImportError:
        return logging.Formatter(fmt)


def get_logger_config(config, loggers):

    if hasattr(config, "logging_level"):
        log_level = config.logging_level
    else:
        log_level = "INFO"

    if hasattr(config, "logging_file"):
        filename = config.logging_file
    else:
        filename = None

    log_level = os.environ.get("QUETZ_LOG_LEVEL", log_level)

    log_level = log_level.upper()

    handlers = ["console"]
    if filename:
        handlers.append("file")

    LOG_FORMATTERS = {
        "colour": {
            "()": "quetz.config.colourized_formatter",
            "fmt": "%(levelprefix)s [%(name)s] %(message)s",
            "use_colors": True,
        },
        "basic": {"format": "%(levelprefix)s [%(name)s] %(message)s"},
        "timestamp": {"format": '%(asctime)s %(levelname)s %(name)s  %(message)s'},
    }

    curdir = os.getcwd()

    LOG_HANDLERS = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "colour",
            "level": log_level,
            "stream": "ext://sys.stderr",
        },
        "file": {
            "class": "logging.FileHandler",
            "formatter": "timestamp",
            "filename": filename or os.path.join(curdir, "quetz.log"),
            "level": log_level,
        },
    }

    LOGGERS = {k: {"level": log_level, "handlers": handlers} for k in loggers}

    LOG_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": LOG_FORMATTERS,
        "handlers": LOG_HANDLERS,
        "loggers": LOGGERS,
    }

    return LOG_CONFIG


def configure_logger(config=None, loggers=("quetz", "urllib3.util.retry", "alembic")):
    """Get quetz logger"""

    log_config = get_logger_config(config, loggers)

    logging.config.dictConfig(log_config)


def get_plugin_manager(config=None) -> pluggy.PluginManager:
    """Create an instance of plugin manager."""

    if not config:
        config = Config()

    pm = pluggy.PluginManager("quetz")
    pm.add_hookspecs(hooks)
    if config.configured_section("plugins"):
        for name in config.plugins_enabled:
            pm.load_setuptools_entrypoints("quetz", name)
    else:
        pm.load_setuptools_entrypoints("quetz")
    return pm
