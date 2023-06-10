import logging
import os
import tempfile

import pytest

# from quetz.config import Config, ConfigEntry, ConfigSection, configure_logger
from quetz.config import Config, Settings, configure_logger
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

    # check if it works with path even if QUETZ_CONFIG_FILE is
    # not defined
    with tempfile.NamedTemporaryFile("w", delete=False) as fid:
        fid.write(config_str)
        fid.flush()
        config = Config(fid.name)
    assert config.configured_section("users")


def test_config_users(config):
    config = Config()
    assert config.users.default_role == "member"
    assert config.users.create_default_channel
    assert config.users.admins == ["bartosz"]
    assert not config.users.maintainers
    assert not config.users.members


@pytest.mark.parametrize(
    "config_extra", ["[users]\nadmins=[]", "[users]\nmaintainers=[]"]
)
def test_config_empty_users_section(dao: Dao, user, config):
    config = Config()
    assert config.configured_section("users")
    assert not config.users.admins
    assert not config.users.maintainers
    assert not config.users.members
    assert not config.users.default_role
    assert not config.users.create_default_channel


def test_config_is_singleton(config):
    config = Config()
    c = Config()

    assert c is config

    Config._instances = {}

    c_new = Config()

    assert c_new is not config

    c_file = Config()

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
    assert c_one.users.admins == ["one"]

    c_other = Config(other_path)

    assert c_other.configured_section("users")
    assert c_other.users.admins == ["other"]

    c_new = Config(one_path)

    assert c_new is c_one


@pytest.fixture
def _setup_config_extend_require():
    from pydantic import BaseSettings
    from pydantic.error_wrappers import ValidationError

    class OtherPluginSetting(BaseSettings):
        some_config_value: str

    Config.register(other_plugin=(OtherPluginSetting, ...))
    yield
    del Settings.__fields__["other_plugin"]
    del Settings.__annotations__["other_plugin"]


def test_config_extend_require(_setup_config_extend_require, config):
    from pydantic.error_wrappers import ValidationError

    with pytest.raises(ValidationError):
        c = Config()


@pytest.fixture
def setup_config_class():
    from pydantic import BaseSettings

    class ExtraPluginSettings(BaseSettings):
        some: str
        config: str
        has_default: str = "iamdefault"

    Config.register(extra_plugin=(ExtraPluginSettings, ...))
    yield
    del Settings.__fields__["extra_plugin"]
    del Settings.__annotations__["extra_plugin"]


@pytest.mark.parametrize(
    "config_extra", [("[extra_plugin]\nsome=\"testvalue\"\nconfig=\"othervalue\"\n")]
)
def test_config_extend(setup_config_class, config):
    c = Config()
    assert c.extra_plugin.some == 'testvalue'
    assert c.extra_plugin.config == 'othervalue'
    assert c.extra_plugin.has_default == 'iamdefault'


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
