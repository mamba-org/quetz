# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import json
import logging
import os
import random
import shutil
import subprocess
import uuid
from distutils.spawn import find_executable
from enum import Enum
from pathlib import Path
from typing import Dict, NoReturn, Optional

import pkg_resources
import typer
import uvicorn
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.orm.session import Session

from quetz.config import (
    Config,
    _env_config_file,
    _env_prefix,
    _user_dir,
    configure_logger,
    create_config,
)
from quetz.dao import Dao
from quetz.database import get_session
from quetz.db_models import (
    ApiKey,
    Channel,
    ChannelMember,
    Identity,
    Package,
    PackageMember,
    Profile,
    User,
)

app = typer.Typer()

_deployments_file = os.path.join(_user_dir, 'deployments.json')

logger = logging.getLogger("quetz-cli")
configure_logger(loggers=("quetz-cli", "alembic"))


class LogLevel(str, Enum):
    critical = "critical"
    error = "error"
    warning = "warning"
    info = "info"
    debug = "debug"
    trace = "trace"


def _alembic_config(db_url: str) -> AlembicConfig:
    script_location = "quetz:migrations"

    migration_modules = [
        f"{entry_point.module_name}:versions"
        for entry_point in pkg_resources.iter_entry_points('quetz.migrations')
    ]
    migration_modules.append("quetz:migrations/versions")

    version_locations = " ".join(migration_modules)

    alembic_cfg = AlembicConfig()
    alembic_cfg.set_main_option('script_location', script_location)
    alembic_cfg.set_main_option('version_locations', version_locations)
    alembic_cfg.set_main_option('sqlalchemy.url', db_url)
    return alembic_cfg


def _run_migrations(
    db_url: Optional[str] = None,
    alembic_config: Optional[AlembicConfig] = None,
    branch_name: str = "heads",
) -> None:
    logger.info('Running DB migrations on %r', db_url)
    if not alembic_config and db_url:
        alembic_config = _alembic_config(db_url)
    command.upgrade(alembic_config, branch_name)


def _make_migrations(
    db_url: Optional[str],
    message: str,
    plugin_name: str = "quetz",
    initialize: bool = False,
    alembic_config: Optional[AlembicConfig] = None,
) -> None:

    if not (db_url or alembic_config):
        raise ValueError("provide either alembic_config or db_url")

    found = False
    for entry_point in pkg_resources.iter_entry_points('quetz.models'):
        logger.debug("loading plugin %r", entry_point.name)
        entry_point.load()
        if entry_point.name == plugin_name:
            found = True

    if not plugin_name == "quetz" and not found:
        raise Exception(
            f"models entrypoint (quetz.models) for plugin {plugin_name} not registered"
        )

    logger.info('Making DB migrations on %r for %r', db_url, plugin_name)
    if not alembic_config and db_url:
        alembic_config = _alembic_config(db_url)

    # find path
    if plugin_name == "quetz":
        version_path = None  # Path(quetz.__file__).parent / 'migrations' / 'versions'
    else:
        entry_point = next(
            pkg_resources.iter_entry_points('quetz.migrations', plugin_name)
        )
        module = entry_point.load()
        version_path = str(Path(module.__file__).parent / "versions")
    if initialize:

        command.revision(
            alembic_config,
            head="base",
            depends_on="quetz",
            message=message,
            autogenerate=True,
            version_path=version_path,
            branch_label=plugin_name,
            splice=True,
        )
    else:
        command.revision(
            alembic_config,
            head=f"{plugin_name}@head",
            message=message,
            autogenerate=True,
            version_path=version_path,
        )


def _init_db(db: Session, config: Config):
    """Initialize the database and add users from config."""

    if config.configured_section("users"):
        dao = Dao(db)
        role_map = [
            (config.users_admins, "owner"),
            (config.users_maintainers, "maintainer"),
            (config.users_members, "member"),
        ]

        for users, role in role_map:
            for username in users:
                logger.info(f"create user {username} with role {role}")
                dao.create_user_with_role(username, role)


def _fill_test_database(db: Session) -> NoReturn:
    """Create dummy users and channels to allow further testing in dev mode."""

    testUsers = []
    try:
        for index, username in enumerate(['alice', 'bob', 'carol', 'dave']):
            user = User(id=uuid.uuid4().bytes, username=username)

            identity = Identity(
                provider='dummy',
                identity_id=str(index),
                username=username,
            )

            profile = Profile(name=username.capitalize(), avatar_url='/avatar.jpg')

            user.identities.append(identity)  # type: ignore
            user.profile = profile
            db.add(user)
            testUsers.append(user)

        for channel_index in range(3):
            channel = Channel(
                name=f'channel{channel_index}',
                description=f'Description of channel{channel_index}',
                private=False,
            )

            for package_index in range(random.randint(5, 10)):
                package = Package(
                    name=f'package{package_index}',
                    summary=f'package {package_index} summary text',
                    description=f'Description of package{package_index}',
                )
                channel.packages.append(package)  # type: ignore

                test_user = testUsers[random.randint(0, len(testUsers) - 1)]
                package_member = PackageMember(
                    package=package, channel=channel, user=test_user, role='owner'
                )

                db.add(package_member)

            if channel_index == 0:
                package = Package(name='xtensor', description='Description of xtensor')
                channel.packages.append(package)  # type: ignore

                test_user = testUsers[random.randint(0, len(testUsers) - 1)]
                package_member = PackageMember(
                    package=package, channel=channel, user=test_user, role='owner'
                )

                db.add(package_member)

                # create API key
                key = uuid.uuid4().hex

                key_user = User(id=uuid.uuid4().bytes)
                api_key = ApiKey(
                    key=key, description='test API key', user=test_user, owner=test_user
                )
                db.add(api_key)
                print(f'Test API key created for user "{test_user.username}": {key}')

                key_package_member = PackageMember(
                    user=key_user,
                    channel_name=channel.name,
                    package_name=package.name,
                    role='maintainer',
                )
                db.add(key_package_member)

            db.add(channel)

            channel_member = ChannelMember(
                channel=channel,
                user=test_user,
                role='owner',
            )

            db.add(channel_member)
        db.commit()
    finally:
        db.close()


def _get_deployments() -> Dict[str, str]:
    """Get a mapping of the current Quetz deployments.

    Returns
    -------
    deployments : Dict[str, str]
        The mapping of deployments
    """

    if os.path.exists(_deployments_file):
        return _get_cleaned_deployments()
    else:
        Path(_user_dir).mkdir(parents=True, exist_ok=True)
        return {}


def _store_deployment(path: str, config_file_name: str) -> NoReturn:
    """Store a new Quetz deployment.

    Parameters
    ----------
    path : str
        The location of the deployment
    config_file_name : str
        The configuration file name, including its extension
    """

    json_ = {path: config_file_name}
    deployments = _get_deployments()

    deployments.update(json_)
    with open(_deployments_file, 'w') as f:
        json.dump(deployments, f)


def _get_cleaned_deployments() -> Dict[str, str]:
    """Get a cleaned version of deployments.

    This could be necessary to clean-up if the user delete manually a deployment
    directory without updating the deployments files in its profile.

    Returns
    -------
    deployments : Dict[str, str]
        The mapping of deployments
    """

    with open(_deployments_file, 'r') as fid:
        deployments: Dict[str, str] = json.load(fid)

    to_delete = []
    for path, f in deployments.items():
        config_file = os.path.join(path, f)
        if not os.path.exists(config_file):  # User has deleted the instance without CLI
            to_delete.append(path)

    cleaned_deployments = {
        path: f for path, f in deployments.items() if path not in to_delete
    }

    if len(to_delete) > 0:
        with open(_deployments_file, 'w') as fid:
            json.dump(cleaned_deployments, fid)

    return cleaned_deployments


def _clean_deployments():
    """Clean the deployments without returning anything."""
    _ = _get_cleaned_deployments()


@app.command()
def init_db(
    path: str = typer.Argument(None, help="The path of the deployment"),
):
    """init database and fill users from config file [users] sections"""

    logger.info("Initializing database")

    config_file = _get_config(path)

    config = Config(config_file)
    os.chdir(path)
    db = get_session(config.sqlalchemy_database_url)

    _run_migrations(config.sqlalchemy_database_url)
    _init_db(db, config)


@app.command()
def make_migrations(
    path: str = typer.Argument(None, help="The path of the deployment"),
    message: str = typer.Option(None, help="revision message"),
    plugin: str = typer.Option("quetz", help="head or heads or plugin name"),
    initialize: bool = typer.Option(False, help="initialize migrations"),
):
    """make database migrations for quetz or a plugin"""

    logger.info("Initializing database")

    config_file = _get_config(path)

    config = Config(config_file)
    os.chdir(path)

    _make_migrations(config.sqlalchemy_database_url, message, plugin, initialize)


@app.command()
def create(
    path: str = typer.Argument(
        None,
        help=(
            "The directory in which the deployment will be created "
            "(will be created if does not exist)"
        ),
    ),
    config_file_name: str = typer.Option(
        "config.toml", help="The configuration file name expected in the provided path"
    ),
    copy_conf: str = typer.Option(
        None, help="The configuration to copy from (e.g. dev_config.toml)"
    ),
    create_conf: bool = typer.Option(
        False,
        help="Enable/disable creation of a default configuration file",
    ),
    dev: bool = typer.Option(
        False,
        help=(
            "Enable/disable dev mode "
            "(fills the database with test data and allows http access)"
        ),
    ),
):
    """Create a new Quetz deployment."""

    logger.info(f"creating new deployment in path {path}")

    abs_path = os.path.abspath(path)
    config_file = os.path.join(path, config_file_name)
    deployments = _get_deployments()

    if os.path.exists(path) and abs_path in deployments:
        delete_ = typer.confirm(f'Quetz deployment exists at {path}.\nOverwrite it?')
        if delete_:
            delete(path, force=True)
            del deployments[abs_path]
        else:
            typer.echo('Use the start command to start a deployment.', err=True)
            raise typer.Abort()

    Path(path).mkdir(parents=True)

    # only authorize path with a config file to avoid deletion of unexpected files
    # when deleting Quetz instance
    if not all(f == config_file_name for f in os.listdir(path)):
        typer.echo(
            f'Quetz deployment not allowed at {path}.\n'
            'The path should not contain more than the configuration file.',
            err=True,
        )
        raise typer.Abort()

    if not os.path.exists(config_file) and not (create_conf or copy_conf):
        typer.echo(
            'No configuration file provided.\n'
            'Use --create-conf or --copy-conf to produce a config file.',
            err=True,
        )
        raise typer.Abort()

    if copy_conf:
        if not os.path.exists(copy_conf):
            typer.echo(f'Config file to copy does not exist {copy_conf}.', err=True)
            raise typer.Abort()

        typer.echo(f"Copying config file from {copy_conf} to {config_file}")
        shutil.copyfile(copy_conf, config_file)

    if not os.path.exists(config_file) and create_conf:
        if dev:
            https = 'false'
        else:
            https = 'true'
        conf = create_config(https=https)
        with open(config_file, 'w') as f:
            f.write(conf)

    os.environ[_env_prefix + _env_config_file] = config_file
    config = Config(config_file)

    os.chdir(path)
    Path('channels').mkdir()
    db = get_session(config.sqlalchemy_database_url)

    _run_migrations(config.sqlalchemy_database_url)
    _init_db(db, config)

    if dev:
        _fill_test_database(db)

    _store_deployment(abs_path, config_file_name)


def _get_config(path: str) -> str:
    """get config path"""

    abs_path = os.path.abspath(path)
    deployments = _get_deployments()

    try:
        config_file_name = deployments[abs_path]
    except KeyError:
        # we can also start the deployment if we find the config file
        config_file_name = 'config.toml'

    config_file = os.path.join(abs_path, config_file_name)
    if not os.path.exists(config_file):
        typer.echo(f'Could not find config at {config_file}')
        raise typer.Abort()
    return config_file


@app.command()
def start(
    path: str = typer.Argument(None, help="The path of the deployment"),
    port: int = typer.Option(8000, help="The port to bind"),
    host: str = typer.Option("127.0.0.1", help="The network interface to bind"),
    proxy_headers: bool = typer.Option(True, help="Enable/disable X-Forwarded headers"),
    log_level: LogLevel = typer.Option(
        LogLevel.info,
        help="Set the logging level",
    ),
    reload: bool = typer.Option(
        False,
        help=(
            "Enable/disable automatic reloading of the server when sources are modified"
        ),
    ),
) -> NoReturn:
    """Start a Quetz deployment.

    To be started, a deployment has to be already created.
    At this time, only Uvicorn is supported as manager.
    """

    logger.info(f"deploying quetz from directory {path}")

    config_file = _get_config(path)

    os.environ[_env_prefix + _env_config_file] = config_file
    os.chdir(path)

    import quetz

    quetz_src = os.path.dirname(quetz.__file__)
    uvicorn.run(
        "quetz.main:app",
        reload=reload,
        reload_dirs=(quetz_src,),
        port=port,
        proxy_headers=proxy_headers,
        host=host,
        log_level=log_level,
    )


@app.command()
def run(
    path: str = typer.Argument(None, help="The path of the deployment"),
    config_file_name: str = typer.Option(
        "config.toml", help="The configuration file name expected in the provided path"
    ),
    copy_conf: str = typer.Option(
        None, help="The configuration to copy from (e.g. dev_config.toml)"
    ),
    create_conf: bool = typer.Option(
        False,
        help="Enable/disable creation of a default configuration file",
    ),
    dev: bool = typer.Option(
        False,
        help=(
            "Enable/disable dev mode "
            "(fills the database with test data and allows http access)"
        ),
    ),
    port: int = typer.Option(8000, help="The port to bind"),
    host: str = typer.Option("127.0.0.1", help="The network interface to bind"),
    proxy_headers: bool = typer.Option(True, help="Enable/disable X-Forwarded headers"),
    log_level: LogLevel = typer.Option(
        LogLevel.info,
        help="Set the logging level",
    ),
    reload: bool = typer.Option(
        False,
        help=(
            "Enable/disable automatic reloading of the server when sources are modified"
        ),
    ),
) -> NoReturn:
    """Run a Quetz deployment.

    It performs sequentially create and start operations."""

    abs_path = os.path.abspath(path)
    create(abs_path, config_file_name, copy_conf, create_conf, dev)
    start(abs_path, port, host, proxy_headers, log_level, reload)


@app.command()
def delete(
    path: str = typer.Argument(None, help="The path of the deployment"),
    force: bool = typer.Option(
        False, help="Enable/disable removal without confirmation prompt"
    ),
) -> NoReturn:
    """Delete a Quetz deployment."""

    abs_path = os.path.abspath(path)
    deployments = _get_deployments()

    try:
        _ = deployments[abs_path]
    except KeyError:
        typer.echo(f'No Quetz deployment found at {path}.', err=True)
        raise typer.Abort()

    delete = force or typer.confirm(f"Delete Quetz deployment at {path}?")
    if not delete:
        raise typer.Abort()

    shutil.rmtree(abs_path)
    _clean_deployments()


@app.command()
def list() -> NoReturn:
    """List Quetz deployments."""

    deployments = _get_deployments()

    if len(deployments) > 0:
        typer.echo('\n'.join([p for p in deployments]))


@app.command()
def plugin(
    cmd: str, path: str = typer.Argument(None, help="Path to the plugin folder")
) -> NoReturn:

    if cmd == 'install':
        abs_path = Path(path).absolute()
        assert (abs_path / "setup.py").exists()

        exes = ['micromamba', 'mamba', 'conda', 'pip']
        if (abs_path / "requirements.txt").exists():
            exe_path = None
            for exe in exes:
                exe_path = find_executable(exe)
                if exe_path:
                    break

            if not exe_path:
                print(
                    f"""Could not find any of {exes}.
                    Needed to install the plugin requirements."""
                )
                exit(1)

            print(f"Installing requirements.txt for {os.path.split(abs_path)[1]}")
            subprocess.call(
                [exe_path, 'install', '--file', abs_path / "requirements.txt"]
            )

        pip_exe_path = find_executable('pip')
        if pip_exe_path:
            subprocess.call([pip_exe_path, 'install', abs_path])
        else:
            print("Could not find pip to install the plugin.")
            exit(1)
    else:
        print(f"Command '{cmd}' not yet understood.")


if __name__ == "__main__":
    app()
