from unittest import mock

import pytest

from quetz import cli
from quetz.db_models import User


@pytest.fixture
def config_extra():
    return """[users]
    admins = ["bartosz"]
    """


def test_init_db(db, config, config_dir):
    def get_db(_):
        return db

    with mock.patch("quetz.cli.get_session", get_db):
        cli.init_db(config_dir)

    user = db.query(User).filter(User.username == "bartosz").one_or_none()

    assert user

    assert user.role == 'owner'
    assert user.username == "bartosz"
    assert not user.profile
