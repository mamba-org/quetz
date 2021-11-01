# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.
import contextlib
import logging
import os
import random
import shutil
import subprocess
import uuid
from distutils.spawn import find_executable
from enum import Enum
from multiprocessing import get_context
from pathlib import Path
from typing import NoReturn, Optional, Union

import typer
import uvicorn
from alembic import command
from alembic.config import Config as AlembicConfig
from importlib_metadata import entry_points
from sqlalchemy.orm.session import Session
from sqlalchemy_utils.functions import database_exists

from quetz.config import (
    Config,
    _env_config_file,
    _env_prefix,
    configure_logger,
    create_config,
)
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

logger = logging.getLogger("quetz-cli")
configure_logger(loggers=("quetz-cli", "alembic"))


class LogLevel(str, Enum):
    critical = "critical"
    error = "error"
    warning = "warning"
    info = "info"
    debug = "debug"
    trace = "trace"


@contextlib.contextmanager
def working_directory(path):
    """Change working directory and return to previous on exit."""
    prev_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)


def _alembic_config(db_url: str) -> AlembicConfig:
    script_location = "quetz:migrations"

    migration_modules = [
        f"{ep.module}:versions"
        for ep in entry_points().select(group='quetz.migrations')
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

    # import the extra models here to register them with sqlalchemy mapper
    # so that it can create the tables
    from quetz.jobs.models import Job, Task  # noqa
    from quetz.metrics.db_models import PackageVersionMetric  # noqa

    for entry_point in entry_points().select(group='quetz.models'):
        logger.debug("loading plugin %r", entry_point.name)
        entry_point.load()
        if entry_point.name == plugin_name:
            found = True

    if plugin_name != "quetz" and not found:
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
        entry_point = tuple(
            entry_points().select(group='quetz.migrations', name=plugin_name)
        )[0]
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


def _set_user_roles(db: Session, config: Config):
    """Initialize the database and add users from config."""
    if config.configured_section("users"):

        role_map = [
            (config.users_admins, "owner"),
            (config.users_maintainers, "maintainer"),
            (config.users_members, "member"),
        ]

        default_role = config.users_default_role

        for users, role in role_map:
            for username in users:
                try:
                    provider, username = username.split(":")
                except ValueError:
                    # use github as default provider
                    raise ValueError(
                        "could not parse the users setting, please provide users in"
                        "the format 'PROVIDER:USERNAME' where PROVIDER is one of"
                        "'google', 'github', 'dummy', etc."
                    )
                logger.info(f"create user {username} with role {role}")
                user = (
                    db.query(User)
                    .join(Identity)
                    .filter(Identity.provider == provider)
                    .filter(User.username == username)
                    .one_or_none()
                )
                if not user:
                    logger.warning(
                        f"could not find user '{username}' "
                        f"with identity from provider '{provider}'"
                    )
                elif user.role is not None and user.role != default_role:
                    logger.warning(
                        f"user has already role {user.role} not assigning a new role"
                    )
                else:
                    user.role = role

        db.commit()


def _fill_test_database(db: Session) -> NoReturn:
    """Create dummy users and channels to allow further testing in dev mode."""
    from quetz.dao import Dao

    test_users = []
    dao = Dao(db)
    try:
        for index, username in enumerate(['alice', 'bob', 'carol', 'dave']):
            user = dao.create_user_with_role(username)

            identity = Identity(
                provider='dummy',
                identity_id=str(index),
                username=username,
            )

            profile = Profile(name=username.capitalize(), avatar_url='/avatar.jpg')

            user.identities.append(identity)  # type: ignore
            user.profile = profile
            db.add(user)
            test_users.append(user)

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

                test_user = test_users[random.randint(0, len(test_users) - 1)]
                package_member = PackageMember(
                    package=package, channel=channel, user=test_user, role='owner'
                )

                db.add(package_member)

            test_user = test_users[random.randint(0, len(test_users) - 1)]

            if channel_index == 0:
                package = Package(name='xtensor', description='Description of xtensor')
                channel.packages.append(package)  # type: ignore

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


def _is_deployment(base_dir: Path):
    config_file = base_dir.joinpath("config.toml")
    if (
        base_dir.exists()
        and config_file.exists()
        and base_dir.joinpath("channels").exists()
    ):
        config = Config(str(config_file.resolve()))
        with working_directory(base_dir):
            return database_exists(config.sqlalchemy_database_url)
    return False


@app.command()
def init_db(
    path: str = typer.Argument(None, help="The path of the deployment"),
):
    """init database and fill users from config file [users] sections"""

    logger.info("Initializing database")

    config = _get_config(path)

    with working_directory(path):
        _run_migrations(config.sqlalchemy_database_url)


@app.command()
def add_user_roles(
    path: str = typer.Argument(None, help="The path of the deployment"),
):
    """Set user roles according to the values from config file [users] sections.

    This command will assign roles only if they were not set before
    (for example using API or an earlier setting in config). The only exception
    is that users who already have a role defined as default_role will have a
    new role set from the config.

    This command will NOT remove roles of existing roles, even if they were
    removed from the config file.
    """

    logger.info("setting up user roles")

    config = _get_config(path)

    with working_directory(path):
        db = get_session(config.sqlalchemy_database_url)
        _set_user_roles(db, config)


@app.command()
def make_migrations(
    path: str = typer.Argument(None, help="The path of the deployment"),
    message: str = typer.Option(None, help="revision message"),
    plugin: str = typer.Option("quetz", help="head or heads or plugin name"),
    initialize: bool = typer.Option(False, help="initialize migrations"),
):
    """make database migrations for quetz or a plugin"""

    logger.info("Initializing database")

    config = _get_config(path)

    with working_directory(path):
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
    copy_conf: str = typer.Option(
        None, help="The configuration to copy from (e.g. dev_config.toml)"
    ),
    create_conf: bool = typer.Option(
        False,
        help="Enable/disable creation of a default configuration file",
    ),
    delete: bool = typer.Option(
        False,
        help="Delete the the deployment if it exists. "
        "Must be specified with --copy-conf or --create-conf",
    ),
    exists_ok: bool = typer.Option(
        False, help="Skip the creation if deployment already exists."
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
    deployment_folder = Path(path).resolve()
    config_file = deployment_folder / "config.toml"

    if _is_deployment(deployment_folder):
        if exists_ok:
            logger.info(
                f'Quetz deployment already exists at {deployment_folder}.\n'
                f'Skipping creation.'
            )
            return
        if delete and (copy_conf or create_conf):
            shutil.rmtree(deployment_folder)
        else:
            typer.echo(
                'Use the start command to start a deployment '
                'or specify --delete with --copy-conf or --create-conf.',
                err=True,
            )
            raise typer.Abort()

    deployment_folder.mkdir(parents=True, exist_ok=True)

    # only authorize path with a config file to avoid deletion of unexpected files
    # when deleting Quetz instance
    if any(f != config_file for f in deployment_folder.iterdir()):
        typer.echo(
            f'Quetz deployment not allowed at {path}.\n'
            'The path should not contain more than the configuration file.',
            err=True,
        )
        raise typer.Abort()

    if not config_file.exists() and not create_conf and not copy_conf:
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

    if not config_file.exists() and create_conf:
        https = 'false' if dev else 'true'
        conf = create_config(https=https)
        with open(config_file, 'w') as f:
            f.write(conf)

    os.environ[_env_prefix + _env_config_file] = str(config_file.resolve())
    config = Config(str(config_file))

    deployment_folder.joinpath('channels').mkdir(exist_ok=True)
    with working_directory(path):
        db = get_session(config.sqlalchemy_database_url)
        _run_migrations(config.sqlalchemy_database_url)
        if dev:
            _fill_test_database(db)
        _set_user_roles(db, config)


def _get_config(path: Union[Path, str]) -> Config:
    """get config path"""
    config_file = Path(path) / 'config.toml'
    if not config_file.exists():
        typer.echo(f'Could not find config at {config_file}')
        raise typer.Abort()

    config = Config(str(config_file.resolve()))
    if not os.environ.get(_env_prefix + _env_config_file):
        os.environ[_env_prefix + _env_config_file] = str(config_file.resolve())

    return config


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
    supervisor: bool = typer.Option(
        True,
        help="Start job supervisor with quetz",
    ),
) -> NoReturn:
    """Start a Quetz deployment.

    To be started, a deployment has to be already created.
    At this time, only Uvicorn is supported as manager.
    """

    logger.info(f"deploying quetz from directory {path}")

    deployment_folder = Path(path)
    _get_config(deployment_folder)

    if not _is_deployment(deployment_folder):
        typer.echo(
            'The specified directory is not a deployment.\n'
            'Use the create or run command to create a deployment.',
            err=True,
        )
        raise typer.Abort()

    if supervisor:
        logger.info("starting supervisor")
        ctx = get_context("spawn")
        supervisor_process = ctx.Process(
            target=start_supervisor_daemon,
            args=(deployment_folder,),
        )
        supervisor_process.start()

    with working_directory(path):
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

    if supervisor:
        supervisor_process.terminate()
        supervisor_process.join()


@app.command()
def run(
    path: str = typer.Argument(None, help="The path of the deployment"),
    copy_conf: str = typer.Option(
        None, help="The configuration to copy from (e.g. dev_config.toml)"
    ),
    create_conf: bool = typer.Option(
        False,
        help="Enable/disable creation of a default configuration file",
    ),
    delete: bool = typer.Option(
        False,
        help="Delete the the deployment if it exists. "
        "Must be specified with --copy-conf or --create-conf",
    ),
    skip_if_exists: bool = typer.Option(
        False, help="Skip the creation if deployment already exists."
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
    create(abs_path, copy_conf, create_conf, delete, skip_if_exists, dev)
    start(abs_path, port, host, proxy_headers, log_level, reload)


@app.command()
def delete(
    path: str = typer.Argument(None, help="The path of the deployment"),
    force: bool = typer.Option(
        False, help="Enable/disable removal without confirmation prompt"
    ),
) -> NoReturn:
    """Delete a Quetz deployment."""

    deployment_dir = Path(path)
    if not _is_deployment(deployment_dir):
        typer.echo(f'No Quetz deployment found at {path}.', err=True)
        raise typer.Abort()

    if not force and not typer.confirm(f"Delete Quetz deployment at {path}?"):
        raise typer.Abort()

    shutil.rmtree(deployment_dir)


@app.command()
def plugin(
    cmd: str, path: str = typer.Argument(None, help="Path to the plugin folder")
) -> NoReturn:

    if cmd == 'install':
        abs_path = Path(path).absolute()
        if not (abs_path / "setup.py").exists():
            raise ValueError(f"Could not find any setup.py file in {abs_path}/.")
        requirements = abs_path / "conda-requirements.txt"

        conda_exes = ['mamba', 'conda', 'micromamba']
        conda_exe_path = None
        if requirements.exists():
            for conda_exe in conda_exes:
                conda_exe_path = find_executable(conda_exe)
                if conda_exe_path:
                    break

            if conda_exe_path is None:
                print(
                    f"Could not find any of {', '.join(conda_exes)}. "
                    f"One is needed to install the plugin requirements."
                )
                exit(1)

            print(f"Installing requirements.txt for {os.path.split(abs_path)[1]}")
            subprocess.call(
                [
                    conda_exe_path,
                    'install',
                    '--channel',
                    'conda-forge',
                    '--file',
                    requirements,
                ]
            )

        pip_exe_path = find_executable('pip')
        if pip_exe_path is None:
            # Try to install pip if it's missing
            if conda_exe_path is not None:
                print("pip is missing, installing...")
                subprocess.call(
                    [conda_exe_path, 'install', '--channel', 'conda-forge', 'pip']
                )
                pip_exe_path = find_executable('pip')

        if pip_exe_path is None:
            print("Could not find pip to install the plugin.")
            exit(1)
        subprocess.call([pip_exe_path, 'install', abs_path])
    else:
        print(f"Command '{cmd}' not yet understood.")


def start_supervisor_daemon(path, num_procs=None):
    from quetz.jobs.runner import Supervisor
    from quetz.tasks.workers import get_worker

    configure_logger(loggers=("quetz",))
    config = _get_config(path)
    manager = get_worker(config, num_procs=num_procs)
    with working_directory(path):
        db = get_session(config.sqlalchemy_database_url)
        supervisor = Supervisor(db, manager)
        try:
            supervisor.run()
        except KeyboardInterrupt:
            logger.info("stopping supervisor")
        finally:
            db.close()


@app.command()
def watch_job_queue(
    path: str = typer.Argument(None, help="Path to the plugin folder"),
    num_procs: Optional[int] = typer.Option(
        None, help="Number of processes to use. Default: number of CPU cores"
    ),
) -> None:

    start_supervisor_daemon(path, num_procs)


if __name__ == "__main__":
    app()
