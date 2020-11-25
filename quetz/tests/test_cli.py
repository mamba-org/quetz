from unittest import mock
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from pytest_mock.plugin import MockerFixture

from quetz import cli
from quetz.db_models import Base, User


@pytest.fixture
def user_group():
    return "admins"


@pytest.fixture
def config_extra(user_group):
    if user_group is None:
        return ""
    else:
        return f"""[users]
                {user_group} = ["bartosz"]
                """


def get_user(db, config_dir):
    def get_db(_):
        return db

    with mock.patch("quetz.cli.get_session", get_db):
        cli.init_db(config_dir)

    return db.query(User).filter(User.username == "bartosz").one_or_none()


@pytest.mark.parametrize(
    "user_group,expected_role",
    [("admins", "owner"), ("maintainers", "maintainer"), ("members", "member")],
)
def test_init_db(db, config, config_dir, user_group, expected_role, mocker):
    _run_migrations: MagicMock = mocker.patch("quetz.cli._run_migrations")
    user = get_user(db, config_dir)
    assert user

    assert user.role == expected_role
    assert user.username == "bartosz"
    assert not user.profile
    _run_migrations.assert_called_once()


@pytest.mark.parametrize("user_group", [None])
def test_init_db_no_user(db, config, config_dir, user_group, mocker: MockerFixture):

    _run_migrations: MagicMock = mocker.patch("quetz.cli._run_migrations")
    user = get_user(db, config_dir)

    assert user is None
    _run_migrations.assert_called_once()


def test_init_db_user_exists(db, config, config_dir, user, mocker):
    _run_migrations: MagicMock = mocker.patch("quetz.cli._run_migrations")
    user = get_user(db, config_dir)
    assert user

    assert user.role == 'owner'
    assert user.username == "bartosz"
    _run_migrations.assert_called_once()


@pytest.fixture
def refresh_db(engine, database_url):
    Base.metadata.drop_all(engine)
    try:
        engine.execute("DROP TABLE alembic_version")
    except sa.exc.OperationalError:
        pass


def test_run_migrations(
    sql_connection, engine, database_url, alembic_config, refresh_db
):
    db = sql_connection
    with pytest.raises(sa.exc.DatabaseError):
        db.execute("SELECT * FROM users")

    cli._run_migrations(alembic_config=alembic_config)

    db.execute("SELECT * FROM users")
