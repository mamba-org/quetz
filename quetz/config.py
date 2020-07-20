# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from distutils.util import strtobool
import os
from typing import Any, Optional, NamedTuple, Type

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


def _get_value(entry):
    value = os.getenv(entry.env_var)
    if value:
        return value

    try:
        if entry.section:
            value = __dict[entry.section][entry.name]
        else:
            value = __dict[entry.name]

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


def _load_config(filename):
    with open(filename) as f:
        try:
            t = toml.load(f)
            __dict.update(t)
        except toml.TomlDecodeError as e:
            raise ConfigError(f"failed to load config file '{filename}': {e}")


__dict = dict()
for _dir in (_site_dir, _user_dir):
    _conf = os.path.join(_dir, _filename)
    if os.path.isfile(_conf):
        _load_config(_conf)
_config_env = os.getenv(f"{_env_prefix}{_env_config_file}")
if _config_env and  os.path.isfile(_config_env):
    _load_config(_config_env)
del _dir, _conf


for _entry in _configs:
    _value = _get_value(_entry)
    globals()[_entry.full_name] = _value
del _entry, _value
