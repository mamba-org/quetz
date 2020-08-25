# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from distutils.util import strtobool
import os
from typing import Any, List, NamedTuple, Type, Dict, NoReturn, Union
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
    """An exception class for Quetz configuration errors."""
    pass


class ConfigEntry(NamedTuple):
    """A configuration entry"""

    name: str
    cast: Type
    default: Any = None

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
    """A configuration section."""
    name: str
    entries: List[ConfigEntry]
    required: bool = True


class Config:
    """A configuration of a Quetz deployment."""

    _config_map = (
        ConfigSection("github", [
            ConfigEntry("client_id", str),
            ConfigEntry("client_secret", str)
        ]),
        ConfigSection("sqlalchemy", [
            ConfigEntry("database_url", str)
        ]),
        ConfigSection("session", [
            ConfigEntry("secret", str),
            ConfigEntry("https_only", bool, default=True)
        ])
    )
    _config_dirs = [_site_dir, _user_dir]
    _config_files = [os.path.join(d, _filename) for d in _config_dirs]
    _config_file_env = os.getenv(f"{_env_prefix}{_env_config_file}")

    def __init__(self, deployment_config: str = None) -> NoReturn:
        """Load configurations from various places.

        Order of importance for configuration is:
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
            if (isinstance(item, ConfigSection)
                    and (item.required or item.name in self.config)):
                for entry in item.entries:
                    set_entry_attr(entry, item.name)
            elif isinstance(item, ConfigEntry):
                set_entry_attr(item)

    def _get_value(self, entry: ConfigEntry, section: str = "") \
                   -> Union[str, bool]:
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
                return entry.default

        msg = f"'{entry.name}' unset but no default specified"
        if section:
            msg += f" for section '{section}'"
        raise ConfigError(msg)

    def _read_config(self, filename: str) -> Dict[str, str]:
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
                return toml.load(f)
            except toml.TomlDecodeError as e:
                raise ConfigError(f"failed to load config file '{filename}': {e}")


def create_config(client_id: str = "",
                  client_secret: str = "",
                  database_url: str = "sqlite:///./quetz.sqlite",
                  secret: str = b64encode(token_bytes(32)).decode(),
                  https: str = 'true') -> str:
    """Create a configuration file from a template.

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
