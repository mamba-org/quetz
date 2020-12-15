import logging
import os
import tempfile

import pytest

from quetz.config import Config, ConfigEntry, ConfigSection, configure_logger
from quetz.dao import Dao
from quetz.errors import ConfigError


@pytest.fixture
def config_extra():
    return r"""[users]
admins=["bartosz"]
default_role = "member"
create_default_channel = true
"""


def test_config_without_file_path_set(config_str):

    # the env variable should not be defined for this test to work
    assert not os.environ.get("QUETZ_CONFIG_FILE")

    # we need to check whether Config was not initialised before
    assert not Config._instances
    with pytest.raises(ValueError, match="Environment"):
        Config()

    # check if it works with path even if QUETZ_CONFIG_FILE is
    # not defined
    with tempfile.NamedTemporaryFile("w", delete=False) as fid:
        fid.write(config_str)
        fid.flush()
        config = Config(fid.name)
    assert config.configured_section("users")


def test_config_users(config):
    assert config.users_default_role == "member"
    assert config.users_create_default_channel
    assert config.users_admins == ["bartosz"]
    assert not config.users_maintainers
    assert not config.users_members


@pytest.mark.parametrize(
    "config_extra", ["[users]\nadmins=[]", "[users]\nmaintainers=[]"]
)
def test_config_empty_users_section(dao: Dao, user, config):

    assert config.configured_section("users")
    assert not config.users_admins
    assert not config.users_maintainers
    assert not config.users_members
    assert not config.users_default_role
    assert not config.users_create_default_channel


def test_config_is_singleton(config):

    c = Config()

    assert c is config

    Config._instances = {}

    c_new = Config()

    assert c_new is not config

    c_file = Config("config.toml")

    assert c_file is c_new


def test_config_with_path(config_dir, config_base):

    one_path = os.path.join(config_dir, "one_config.toml")
    other_path = os.path.join(config_dir, "other_config.toml")
    with open(one_path, 'w') as fid:
        fid.write("\n".join([config_base, "[users]\nadmins=['one']"]))
    with open(other_path, 'w') as fid:
        fid.write("\n".join([config_base, "[users]\nadmins=['other']"]))

    Config._instances = {}

    c_one = Config(one_path)

    assert c_one.configured_section("users")
    assert c_one.users_admins == ["one"]

    c_other = Config(other_path)

    assert c_other.configured_section("users")
    assert c_other.users_admins == ["other"]

    c_new = Config(one_path)

    assert c_new is c_one


def test_config_extend_require(config):
    with pytest.raises(ConfigError):
        config.register(
            [
                ConfigSection(
                    "other_plugin",
                    [
                        ConfigEntry("some_config_value", str),
                    ],
                )
            ]
        )
    # remove last entry again
    config._config_map.pop()


@pytest.mark.parametrize(
    "config_extra", ["[extra_plugin]\nsome=\"testvalue\"\nconfig=\"othervalue\"\n"]
)
def test_config_extend(config):
    config.register(
        [
            ConfigSection(
                "extra_plugin",
                [
                    ConfigEntry("some", str),
                    ConfigEntry("config", str),
                    ConfigEntry("has_default", str, "iamdefault"),
                ],
            )
        ]
    )

    assert config.extra_plugin_some == 'testvalue'
    assert config.extra_plugin_config == 'othervalue'
    assert config.extra_plugin_has_default == 'iamdefault'

    config._config_map.pop()


def test_configure_logger(capsys):
    "configure_logger should be idempotent"

    configure_logger()
    logger = logging.getLogger("quetz")
    logger.error("my test")

    captured = capsys.readouterr()
    assert "[quetz]" in captured.err
    assert "ERROR" in captured.err
    assert "my test" in captured.err
    assert len(captured.err.splitlines()) == 1

    captured = capsys.readouterr()
    assert not captured.err

    configure_logger()
    logger.info("second")
    captured = capsys.readouterr()
    assert "[quetz]" in captured.err
    assert "INFO" in captured.err
    assert "second" in captured.err
    assert captured.err.count("second") == 1
    assert "my test" not in captured.err
    assert len(captured.err.splitlines()) == 1
