# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from distutils.util import strtobool
import os
from typing import Any, Optional, NamedTuple, Type
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


_configs = (
    ConfigEntry("client_id", str, section="github", required=True),
    ConfigEntry("client_secret", str, section="github", required=True),
    ConfigEntry("database_url", str, section="sqlalchemy", required=True),
    ConfigEntry("secret", str, section="session", required=True),
    ConfigEntry("https_only", bool, section="session", default=True)
)


def _get_value(entry, config):
    value = os.getenv(entry.env_var)
    if value:
        return entry.casted(value)

    try:
        if entry.section:
            value = config[entry.section][entry.name]
        else:
            value = config[entry.name]

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


def _read_config(filename):
    with open(filename) as f:
        try:
            t = toml.load(f)
            return t
        except toml.TomlDecodeError as e:
            raise ConfigError(f"failed to load config file '{filename}': {e}")


def create_config(client_id: str = "",
                  client_secret: str = "", 
                  database_url: str = "sqlite:///./quetz.sqlite",
                  secret: str = b64encode(token_bytes(32)).decode()):

    with open(os.path.join(os.path.dirname(__file__), "config.toml"), 'r') as f:
        config = ''.join(f.readlines())

    return config.format(client_id, client_secret, database_url, secret)


def load_configs(configuration: str = None):

    config = {}
    config_dirs = [_site_dir, _user_dir]
    config_files = [os.path.join(d, _filename) for d in config_dirs]
    config_env = os.getenv(f"{_env_prefix}{_env_config_file}")

    for f in (config_env, configuration):
        if f and os.path.isfile(f):
            config_files.append(f)

    for f in config_files:
        if os.path.isfile(f):
            config.update(_read_config(f))

    for entry in _configs:
        value = _get_value(entry, config)
        globals()[entry.full_name] = value
