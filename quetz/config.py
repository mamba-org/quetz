# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from distutils.util import strtobool
import os
from typing import Any, NamedTuple, Type, Dict, NoReturn, Union
from secrets import token_bytes
from base64 import b64encode

import appdirs
import toml


_filename = "config.toml"
_env_prefix = "QUETZ_"
_env_config_file = "CONFIG_FILE"
_site_dir = appdirs.site_config_dir("quetz")
_user_dir = appdirs.user_config_dir("quetz")


class ConfigError(Exception):
    pass


class ConfigEntry(NamedTuple):
    name: str
    cast: Type
    section: str = None
    required: bool = False
    default: Any = None

    @property
    def full_name(self):
        if self.section:
            return f"{self.section}_{self.name}"
        return self.name

    @property
    def env_var(self):
        if self.section:
            return f"{_env_prefix}{self.full_name.upper()}"
        return f"{_env_prefix}{self.name.upper()}"

    def casted(self, value):
        if self.cast is bool:
            try:
                return strtobool(str(value))
            except ValueError as e:
                raise ConfigError(f"{self.name}: {e}")

        return self.cast(value)


class Config:
    _config_map = (
        ConfigEntry("client_id", str, section="github", required=True),
        ConfigEntry("client_secret", str, section="github", required=True),
        ConfigEntry("database_url", str, section="sqlalchemy", required=True),
        ConfigEntry("secret", str, section="session", required=True),
        ConfigEntry("https_only", bool, section="session", default=True)
    )
    _config_dirs = [_site_dir, _user_dir]
    _config_files = [os.path.join(d, _filename) for d in _config_dirs]
    _config_file_env = os.getenv(f"{_env_prefix}{_env_config_file}")

    def __init__(self, deployment_config: str = None) -> NoReturn:
        """ Load configurations from various places.

        Order of importance for configuration is :
        host < user profile < deployment < configuration file from env var < value from env var

        Parameters
        ----------
        deployment_config : str, optional
            The configuration stored at deployment level
        """

        self.config = {}

        for f in (deployment_config, self._config_file_env):
            if f and os.path.isfile(f):
                self._config_files.append(f)

        # In order, get configuration from:
        # _site_dir, _user_dir, deployment_config, config_file_env
        for f in self._config_files:
            if os.path.isfile(f):
                self.config.update(self._read_config(f))

        for entry in self._config_map:
            env_var_value = os.getenv(entry.env_var)

            # Override the configuration files if an env variable is defined for
            # the entry.
            if env_var_value:
                value = entry.casted(env_var_value)
            else:
                value = self._get_value(entry)

            setattr(self, entry.full_name, value)

    def _get_value(self, entry: ConfigEntry) -> Union[str, bool]:
        """ Get an entry value from a configuration mapping.

        Parameters
        ----------
        entry : ConfigEntry
            The entry to search

        Returns
        -------
        value : Union[str, bool]
            The entry value
        """
        try:
            if entry.section:
                value = self.config[entry.section][entry.name]
            else:
                value = self.config[entry.name]

            return entry.casted(value)

        except KeyError:
            if entry.required:
                if entry.section:
                    raise ConfigError(
                        f"'{entry.name}' not found for section '{entry.section}'")
                raise ConfigError(f"'{entry.name}' not found")

            if entry.default:
                return entry.default

        raise ConfigError(f"'{entry.name}' unset but no default specified")

    def _read_config(self, filename: str) -> Dict[str, str]:
        """ Read a configuration file from its path.

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
                return toml.load(f)
            except toml.TomlDecodeError as e:
                raise ConfigError(f"failed to load config file '{filename}': {e}")


def create_config(client_id: str = "",
                  client_secret: str = "",
                  database_url: str = "sqlite:///./quetz.sqlite",
                  secret: str = b64encode(token_bytes(32)).decode(),
                  https: str = 'true') -> str:
    """ Create a configuration file from a template.

    Parameters
    ----------
    client_id : str, optional
        The Github client ID {default=""}
    client_secret : str, optional
        The Github client secret {default=""}
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
