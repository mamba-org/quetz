import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

import pkg_resources
import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
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


def get_user(db, config_dir, username="bartosz"):
    def get_db(_):
        return db

    with mock.patch("quetz.cli.get_session", get_db):
        cli.init_db(config_dir)

    return db.query(User).filter(User.username == username).one_or_none()


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


@pytest.mark.parametrize("config_extra", ['[users]\nadmins = ["alice"]\n'])
def test_init_db_create_test_users(db, config, mocker, config_dir):

    _run_migrations: MagicMock = mocker.patch("quetz.cli._run_migrations")

    def get_db(_):
        return db

    with mock.patch("quetz.cli.get_session", get_db):
        cli.create(
            Path(config_dir) / "new-deployment",
            config_file_name="config.toml",
            copy_conf="config.toml",
            create_conf=None,
            dev=True,
        )

    user = db.query(User).filter(User.username == "alice").one_or_none()

    assert user.role == "owner"

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

    revision.assert_called_with(
        mock.ANY,
        message="test revision",
        autogenerate=True,
        head="quetz@head",
        version_path=None,
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


alembic_env = """
from alembic import context

config = context.config

from sqlalchemy import MetaData
target_metadata = MetaData()

connectable = config.attributes.get('connection')

with connectable.connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
"""

script_mako = """
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}

def upgrade(): pass

def downgrade(): pass
"""

quetz_rev = """
revision = "0000"
down_revision = None
branch_labels = ("quetz", )
depends_on = None

def upgrade(): pass

def downgrade(): pass
"""


def test_multi_head(
    config, config_dir, entry_points: Path, alembic_config, engine, refresh_db
):

    quetz_migrations_path = Path(config_dir) / "migrations"
    quetz_versions_path = quetz_migrations_path / "versions"

    alembic_config.config_file_name = quetz_migrations_path / "alembic.ini"

    os.makedirs(quetz_versions_path)

    plugin_versions_path = Path(entry_points) / "versions"

    with open(quetz_migrations_path / "env.py", "w") as fid:
        fid.write(alembic_env)
    with open(quetz_migrations_path / "script.py.mako", "w") as fid:
        fid.write(script_mako)
    with open(quetz_versions_path / "0000_initial.py", 'w') as fid:
        fid.write(quetz_rev)

    alembic_config.set_main_option(
        "version_locations",
        " ".join(map(str, [plugin_versions_path, quetz_versions_path])),
    )
    alembic_config.set_main_option("script_location", str(quetz_migrations_path))
    cli._run_migrations(alembic_config=alembic_config)

    # initialize a plugin
    cli._make_migrations(
        None,
        message="test revision",
        plugin_name="quetz-plugin",
        initialize=True,
        alembic_config=alembic_config,
    )
    cli._run_migrations(alembic_config=alembic_config)

    rev_file = next((plugin_versions_path).glob("*test_revision.py"))
    with open(rev_file) as fid:
        content = fid.read()
    assert 'down_revision = None' in content
    assert "depends_on = 'quetz'" in content
    import re

    m = re.search("revision = '(.*)'", content)
    assert m
    plugin_rev_1 = m.groups()[0]

    # second revision quetz
    cli._make_migrations(
        None,
        message="test revision",
        alembic_config=alembic_config,
    )
    cli._run_migrations(alembic_config=alembic_config)

    rev_file = next((quetz_versions_path).glob("*test_revision.py"))
    with open(rev_file) as fid:
        content = fid.read()
    assert "down_revision = '0000'" in content

    # second revision plugin
    cli._make_migrations(
        None,
        message="plugin rev 2",
        plugin_name="quetz-plugin",
        alembic_config=alembic_config,
    )
    rev_file = next((plugin_versions_path).glob("*plugin_rev_2.py"))

    with open(rev_file) as fid:
        content = fid.read()
    assert f"down_revision = '{plugin_rev_1}'" in content

    cli._run_migrations(alembic_config=alembic_config)

    # check heads

    script_directory = ScriptDirectory.from_config(alembic_config)
    heads = script_directory.get_revisions("heads")
    assert len(heads) == 2

    for p in (plugin_versions_path).glob("*.py"):
        os.remove(p)

    try:
        engine.execute("DROP TABLE alembic_version")
    except sa.exc.DatabaseError:
        pass
