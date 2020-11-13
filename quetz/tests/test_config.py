import pytest

from quetz.config import Config
from quetz.dao import Dao


@pytest.fixture
def config_extra():
    return r"""[users]
admins=["bartosz"]
default_role = "member"
create_default_channel = true
"""


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

    Config._instance = None

    c_new = Config()

    assert c_new is not config
