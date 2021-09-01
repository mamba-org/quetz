import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from pytest_mock.plugin import MockerFixture
from typer.testing import CliRunner

from quetz import cli
from quetz.config import Config
from quetz.db_models import Base, Identity, User

runner = CliRunner()


@pytest.fixture
def user_group():
    return "admins"


@pytest.fixture
def default_role():
    return None


@pytest.fixture
def config_extra(user_group, default_role):
    config_values = ["[users]"]
    if user_group is not None:
        config_values.append(f'{user_group} = ["github:bartosz"]')
    if default_role:
        config_values.append(f"{default_role=}")
    return "\n".join(config_values)


@pytest.fixture
def user_with_identity(user, db):
    identity = Identity(user=user, provider="github", identity_id="1")
    db.add(identity)
    db.commit()
    return identity


def get_user(db, config_dir, username="bartosz"):
    def get_db(_):
        return db

    with mock.patch("quetz.cli.get_session", get_db):
        cli.add_user_roles(config_dir)

    return db.query(User).filter(User.username == username).one_or_none()


def test_init_db(db, config, config_dir, mocker):
    _run_migrations: MagicMock = mocker.patch("quetz.cli._run_migrations")
    cli.init_db(config_dir)
    _run_migrations.assert_called_once()


@pytest.mark.parametrize(
    "user_group,expected_role",
    [("admins", "owner"), ("maintainers", "maintainer"), ("members", "member")],
)
def test_create_user_from_config(
    db, config, config_dir, user_group, expected_role, mocker, user_with_identity
):

    user = get_user(db, config_dir)
    assert user

    assert user.role == expected_role
    assert user.username == "bartosz"


@pytest.mark.parametrize("user_group", [None])
def test_set_user_roles_no_user(
    db, config, config_dir, user_group, mocker: MockerFixture
):

    user = get_user(db, config_dir)

    assert user is None


def test_set_user_roles_user_exists(
    db, config, config_dir, user, mocker, user_with_identity
):
    user = get_user(db, config_dir)
    assert user

    assert user.role == 'owner'
    assert user.username == "bartosz"


@pytest.mark.parametrize("default_role", [None, "member"])
@pytest.mark.parametrize("current_role", ['owner', 'member', 'maintainer'])
def test_set_user_roles_user_has_role(
    db, config, config_dir, user, mocker, user_with_identity, current_role, default_role
):
    user.role = current_role
    db.commit()
    user = get_user(db, config_dir)
    assert user

    # role shouldn't be changed unless it's default role
    if current_role != default_role:
        assert user.role == current_role
    else:
        assert user.role == "owner"
    assert user.username == "bartosz"


@pytest.mark.parametrize("config_extra", ['[users]\nadmins = ["dummy:alice"]\n'])
def test_init_db_create_test_users(db, config, mocker, config_dir):

    _run_migrations: MagicMock = mocker.patch("quetz.cli._run_migrations")

    def get_db(_):
        return db

    with mock.patch("quetz.cli.get_session", get_db):
        cli.create(
            Path(config_dir) / "new-deployment",
            copy_conf="config.toml",
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
    config, sql_connection, engine, database_url, alembic_config, refresh_db
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
def dummy_migration_plugin() -> Path:

    path = Path(tempfile.mkdtemp(prefix="quetz"))
    plugin_dir = str(path)
    pkg_path = path / "dummy"

    os.makedirs(pkg_path / "versions")
    with open(pkg_path / "dummy_module.py", 'w') as fid:
        fid.write("class DummyPlugin: pass")
    with open(pkg_path / "__init__.py", 'w') as fid:
        fid.write("")

    # add entry points
    os.makedirs(path / "dummy-0.0.0.dist-info")
    with open(path / "dummy-0.0.0.dist-info" / "entry_points.txt", 'w') as fid:
        fid.writelines(
            [
                "[quetz.models]\nquetz-plugin = dummy.dummy_module\n",
                "[quetz.migrations]\nquetz-plugin = dummy",
            ]
        )

    sys.path.insert(0, plugin_dir)

    yield pkg_path

    shutil.rmtree(path, ignore_errors=True)
    sys.path.remove(plugin_dir)


def test_make_migrations_plugin(mocker, config, config_dir, dummy_migration_plugin):

    revision = mocker.patch("alembic.command.revision")

    # initialize a plugin
    cli.make_migrations(
        config_dir, message="test revision", plugin="quetz-plugin", initialize=True
    )

    version_path = os.path.join(dummy_migration_plugin, "versions")
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
    config, config_dir, dummy_migration_plugin: Path, alembic_config, engine
):

    # make sure db is up-to-date
    cli._run_migrations(alembic_config=alembic_config)

    alembic_config.set_main_option(
        "version_locations",
        os.path.join(dummy_migration_plugin, "versions") + " quetz:migrations/versions",
    )

    # initialize a plugin
    cli._make_migrations(
        None,
        message="test revision",
        plugin_name="quetz-plugin",
        initialize=True,
        alembic_config=alembic_config,
    )

    migration_scripts = list(
        (dummy_migration_plugin / "versions").glob("*_test_revision.py")
    )
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

    migration_scripts = list(
        (dummy_migration_plugin / "versions").glob("*_new_revision.py")
    )
    assert migration_scripts

    with open(migration_scripts[0]) as fid:
        content = fid.read()

    assert "test_plugin_table" in content

    # clean up

    for p in (dummy_migration_plugin / "versions").glob("*.py"):
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
    config, config_dir, dummy_migration_plugin: Path, alembic_config, engine, refresh_db
):

    quetz_migrations_path = Path(config_dir) / "migrations"
    quetz_versions_path = quetz_migrations_path / "versions"

    alembic_config.config_file_name = quetz_migrations_path / "alembic.ini"

    os.makedirs(quetz_versions_path)

    plugin_versions_path = Path(dummy_migration_plugin) / "versions"

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


def test_create_exists_ok():
    """Nothing happens if --exists-ok is enabled."""
    with mock.patch("quetz.cli._is_deployment", lambda x: True):
        res = runner.invoke(cli.app, ["create", "test", "--exists-ok"])
        assert res.exit_code == 0


wrong_cli_args = [
    ["create", "test"],
    ["create", "test", "--copy-conf", "config.toml"],
    ["create", "test", "--create-conf"],
    ["create", "test", "--copy-conf", "config.toml", "--create-conf"],
    ["create", "test", "--delete"],
]


@pytest.mark.parametrize('cli_args', wrong_cli_args)
def test_create_exists_errors(cli_args):
    """Create command raises if deployment exists and not force deleted."""
    with mock.patch("quetz.cli._is_deployment", lambda x: True):
        res = runner.invoke(cli.app, cli_args)
        assert res.exit_code == 1
        assert (
            res.output == "Use the start command to start a deployment "
            "or specify --delete with --copy-conf or --create-conf.\nAborted!\n"
        )


@pytest.fixture()
def empty_deployment_dir() -> Path:
    path = Path(tempfile.mkdtemp()).resolve()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture()
def empty_config_on_exit() -> None:
    yield
    try:
        del os.environ["QUETZ_CONFIG_FILE"]
    except KeyError:
        pass
    Config._instances = {}


def test_create_conf(empty_deployment_dir: Path, empty_config_on_exit: None):
    """Create command with create conf cretes the needed files and folder."""
    runner.invoke(cli.app, ['create', str(empty_deployment_dir), '--create-conf'])
    assert empty_deployment_dir.joinpath('config.toml').exists()
    assert empty_deployment_dir.joinpath('channels').exists()
    assert empty_deployment_dir.joinpath('quetz.sqlite').exists()


def test_create_exists_delete(empty_deployment_dir: Path, empty_config_on_exit: None):
    """Existing deployment is removed if delete arg is used."""
    runner.invoke(cli.app, ['create', str(empty_deployment_dir), '--create-conf'])
    creation_time = empty_deployment_dir.stat().st_mtime
    runner.invoke(
        cli.app, ['create', str(empty_deployment_dir), '--delete', '--create-conf']
    )
    assert empty_deployment_dir.stat().st_mtime > creation_time
    assert empty_deployment_dir.joinpath('config.toml').exists()
    assert empty_deployment_dir.joinpath('channels').exists()
    assert empty_deployment_dir.joinpath('quetz.sqlite').exists()


def test_create_no_config(empty_deployment_dir: Path, empty_config_on_exit: None):
    """Error on create command with empty deployment and no config."""
    res = runner.invoke(cli.app, ['create', str(empty_deployment_dir)])
    assert res.exit_code == 1
    assert "No configuration file provided." in res.output


def test_create_extra_file_in_deployment(
    empty_deployment_dir: Path, empty_config_on_exit: None
):
    """Error on create command with extra files in deployment."""
    empty_deployment_dir.joinpath('extra_file.txt').touch()
    res = runner.invoke(cli.app, ['create', str(empty_deployment_dir)])
    assert res.exit_code == 1
    assert "Quetz deployment not allowed at" in res.output


def test_create_missing_copy_conf(
    empty_deployment_dir: Path, empty_config_on_exit: None
):
    """Error on create command with wrong copy-conf path."""
    res = runner.invoke(
        cli.app, ['create', str(empty_deployment_dir), "--copy-conf", "none.toml"]
    )
    assert res.exit_code == 1
    assert "Config file to copy does not exist" in res.output
