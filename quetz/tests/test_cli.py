import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

import pkg_resources
import pytest
import sqlalchemy as sa
from pytest_mock.plugin import MockerFixture

import quetz
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
    except sa.exc.DatabaseError:
        pass


def test_run_migrations(
    sql_connection, engine, database_url, alembic_config, refresh_db
):
    db = sql_connection
    with pytest.raises(sa.exc.DatabaseError):
        db.execute("SELECT * FROM users")

    cli._run_migrations(alembic_config=alembic_config)

    db.execute("SELECT * FROM users")


def test_make_migrations_quetz(mocker, config, config_dir):
    revision = mocker.patch("alembic.command.revision")

    # new revision for main tree
    cli.make_migrations(
        config_dir, message="test revision", plugin="quetz", initialize=False
    )

    quetz_migrations_path = Path(quetz.__file__).parent / 'migrations'

    revision.assert_called_with(
        mock.ANY,
        message="test revision",
        autogenerate=True,
        head="quetz@head",
        version_path=str(quetz_migrations_path / "versions"),
    )


@pytest.fixture(scope="module")
def entry_points() -> Path:

    path = Path(tempfile.mkdtemp())

    # add entry points
    dist = pkg_resources.Distribution(str(path))
    ep = pkg_resources.EntryPoint.parse("quetz-plugin = dummy_module", dist=dist)

    with open(path / "dummy_module.py", 'w') as fid:
        fid.write("class DummyPlugin: pass")
    os.makedirs(path / "versions")
    dist._ep_map = {  # type: ignore
        "quetz.models": {"quetz-plugin": ep},
        "quetz.migrations": {"quetz-plugin": ep},
    }

    pkg_resources.working_set.add(dist, "dummy")

    yield path

    shutil.rmtree(path, ignore_errors=True)


def test_make_migrations_plugin(mocker, config, config_dir, entry_points):

    revision = mocker.patch("alembic.command.revision")

    # initialize a plugin
    cli.make_migrations(
        config_dir, message="test revision", plugin="quetz-plugin", initialize=True
    )

    version_path = os.path.join(entry_points, "versions")
    revision.assert_called_with(
        mock.ANY,
        message="test revision",
        autogenerate=True,
        head="base",
        depends_on="quetz",
        version_path=version_path,
        branch_label="quetz-plugin",
        splice=True,
    )

    # add revision to a plugin
    cli.make_migrations(
        config_dir, message="revision v2", plugin="quetz-plugin", initialize=False
    )
    revision.assert_called_with(
        mock.ANY,
        message="revision v2",
        autogenerate=True,
        head="quetz-plugin@head",
        version_path=version_path,
    )


def test_make_migrations_plugin_with_alembic(
    config, config_dir, entry_points: Path, alembic_config, engine
):

    # make sure db is up-to-date
    cli._run_migrations(alembic_config=alembic_config)

    alembic_config.set_main_option(
        "version_locations",
        os.path.join(entry_points, "versions") + " quetz:migrations/versions",
    )

    # initialize a plugin
    cli._make_migrations(
        None,
        message="test revision",
        plugin_name="quetz-plugin",
        initialize=True,
        alembic_config=alembic_config,
    )

    migration_scripts = list((entry_points / "versions").glob("*_test_revision.py"))
    assert migration_scripts

    # apply migrations
    cli._run_migrations(alembic_config=alembic_config)

    # add a new revision

    class TestPluginModel(Base):
        __tablename__ = "test_plugin_table"
        pk = sa.Column(sa.String, primary_key=True)

    cli._make_migrations(
        None,
        message="new revision",
        plugin_name="quetz-plugin",
        alembic_config=alembic_config,
    )

    migration_scripts = list((entry_points / "versions").glob("*_new_revision.py"))
    assert migration_scripts

    with open(migration_scripts[0]) as fid:
        content = fid.read()

    assert "test_plugin_table" in content

    # clean up

    for p in (entry_points / "versions").glob("*.py"):
        os.remove(p)

    Base.metadata.drop_all(engine)
    try:
        engine.execute("DROP TABLE alembic_version")
    except sa.exc.DatabaseError:
        pass


def xtest_multi_head(config, config_dir, entry_points: Path, alembic_config, engine):
    cli._run_migrations(alembic_config=alembic_config)

    alembic_config.set_main_option(
        "version_locations",
        os.path.join(entry_points, "versions") + " quetz:migrations/versions",
    )

    # initialize a plugin
    cli._make_migrations(
        None,
        message="test revision",
        plugin_name="quetz-plugin",
        initialize=True,
        alembic_config=alembic_config,
    )
    cli._run_migrations(alembic_config=alembic_config)

    # second revision
    cli._make_migrations(
        None,
        message="test revision 2",
        plugin_name="quetz-plugin",
        alembic_config=alembic_config,
    )

    # reset db
    engine.execute("DROP TABLE alembic_version")
    Base.metadata.drop_all(engine)

    alembic_config.set_main_option(
        "version_locations",
        "quetz:migrations/versions",
    )
    cli._run_migrations(alembic_config=alembic_config)
    # add quetz revision

    cli._make_migrations(
        None,
        message="quetz revision",
        plugin_name="quetz",
        alembic_config=alembic_config,
    )

    alembic_config.set_main_option(
        "version_locations",
        os.path.join(entry_points, "versions") + " quetz:migrations/versions",
    )
    from alembic import command

    command.heads(alembic_config)
    1 / 0

    # clean up

    for p in (entry_points / "versions").glob("*.py"):
        os.remove(p)

    quetz_versions = Path(quetz.__file__).parent / "migrations" / "versions"
    for p in (entry_points / "versions").glob("*.py"):
        os.remove(p)
    for p in (quetz_versions).glob("*quetz_revision.py"):
        os.remove(p)

    Base.metadata.drop_all(engine)
    try:
        engine.execute("DROP TABLE alembic_version")
    except sa.exc.DatabaseError:
        pass
