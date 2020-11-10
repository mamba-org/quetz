import pytest

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
    assert not hasattr(config, "maintainers")
    assert not hasattr(config, "members")


@pytest.mark.xfail
def test_config_user_role(dao: Dao, user, config):
    user = dao.get_user_by_username(user.username)

    assert user.role == 'member'
