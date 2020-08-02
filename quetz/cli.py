# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import typer
import os
import shutil
import uvicorn
import json
import random
import uuid
from pathlib import Path

from quetz.config import (create_config, load_configs, _user_dir, _env_prefix,
                          _env_config_file)
from quetz.database import init_db, get_session
from quetz.db_models import (User, Identity, Profile, Channel, ChannelMember, Package,
                             PackageMember, ApiKey)

app = typer.Typer()

_deployements_file = os.path.join(_user_dir, 'deployements.json')


def _fill_test_database():
    db = get_session()
    testUsers = []
    try:
        for index, username in enumerate(['alice', 'bob', 'carol', 'dave']):
            user = User(id=uuid.uuid4().bytes, username=username)

            identity = Identity(
                provider='dummy',
                identity_id=str(index),
                username=username,
            )

            profile = Profile(
                name=username.capitalize(),
                avatar_url='/avatar.jpg')

            user.identities.append(identity)
            user.profile = profile
            db.add(user)
            testUsers.append(user)

        for channel_index in range(30):
            channel = Channel(
                name=f'channel{channel_index}',
                description=f'Description of channel{channel_index}',
                private=False)

            for package_index in range(random.randint(5, 100)):
                package = Package(
                    name=f'package{package_index}',
                    description=f'Description of package{package_index}')
                channel.packages.append(package)

                test_user = testUsers[random.randint(0, len(testUsers) - 1)]
                package_member = PackageMember(
                    package=package,
                    channel=channel,
                    user=test_user,
                    role='owner')

                db.add(package_member)

            if channel_index == 0:
                package = Package(
                    name=f'xtensor',
                    description=f'Description of xtensor')
                channel.packages.append(package)

                test_user = testUsers[random.randint(0, len(testUsers) - 1)]
                package_member = PackageMember(
                    package=package,
                    channel=channel,
                    user=test_user,
                    role='owner')

                db.add(package_member)

                # create API key
                key = 'E_KaBFstCKI9hTdPM7DQq56GglRHf2HW7tQtq6si370'

                key_user = User(id=uuid.uuid4().bytes)

                api_key = ApiKey(
                    key=key,
                    description='test API key',
                    user=key_user,
                    owner=test_user
                )
                db.add(api_key)

                key_package_member = PackageMember(
                    user=key_user,
                    channel_name=channel.name,
                    package_name=package.name,
                    role='maintainer')
                db.add(key_package_member)

            db.add(channel)

            channel_member = ChannelMember(
                channel=channel,
                user=testUsers[random.randint(0, len(testUsers)-1)],
                role='owner')

            db.add(channel_member)
        db.commit()
    finally:
        db.close()


def _get_deployements():

    if os.path.exists(_deployements_file):
        return _cleaned_deployements()
    else:
        Path(_user_dir).mkdir(parents=True, exist_ok=True) 
        return {}


def _store_deployement(path: str, config_file_name: str):

    json_ = {path: config_file_name}
    deployements = _get_deployements()

    deployements.update(json_)
    with open(_deployements_file, 'w') as f:
        json.dump(deployements, f)


def _cleaned_deployements():

    with open(_deployements_file, 'r') as f:
        deployements = json.load(f)

    to_delete = []
    for path, f in deployements.items():
        config_file = os.path.join(path, f)
        if not os.path.exists(config_file):  # User has deleted the instance without CLI
            to_delete.append(path)

    cleaned_deployements = {path: f for path, f in deployements.items() 
                            if path not in to_delete}

    if len(to_delete) > 0:
        with open(_deployements_file, 'w') as f:
            json.dump(cleaned_deployements, f)

    return cleaned_deployements


def _clean_deployements():

    _ = _cleaned_deployements()


@app.command()
def create(path: str, 
           config_file_name: str = "config.toml", 
           create_conf: bool = False, 
           test: bool = False):

    abs_path = os.path.abspath(path)
    config_file = os.path.join(path, config_file_name)
    deployements = _get_deployements()

    if os.path.exists(path):
        if abs_path in deployements:
            delete_ = typer.confirm('Quetz deployement exists at {}.\n'.format(path) +
                                    'Overwrite it?')
            if delete_:
                delete(path, force=True)
                create(path, config_file_name, create_conf, test)
                return
            else:
                typer.echo('Use the start command to start a deployement.')
                raise typer.Abort()

        # only authorize path with a config file to avoid deletion of unexpected files
        # when deleting Quetz instance
        if not all([f in [config_file_name] for f in os.listdir(path)]):
            typer.echo('Quetz deployement not allowed at {}.\n'.format(path) +
                       'The path should not contain more than the configuration file.')
            raise typer.Abort()

        if not os.path.exists(config_file) and not create_conf:
            typer.echo('Config file "{}" does not exist at {}.\n'.format(config_file_name,
                                                                         path) + 
                       'Use --create-conf option to generate a default config file.')
            raise typer.Abort()
    else:
        if not create_conf:
            typer.echo('No configuration file provided.\n' + 
                       'Use --create-conf option to generate a default config file.')
            raise typer.Abort()

        Path(path).mkdir(parents=True)

    if not os.path.exists(config_file):
        conf = create_config()
        with open(config_file, 'w') as f:
            f.write(conf)

    os.environ['QUETZ_CONFIG_FILE'] = config_file
    load_configs(config_file)

    os.chdir(path)
    Path('channels').mkdir()
    init_db()
 
    if test:
        _fill_test_database()

    _store_deployement(abs_path, config_file_name)


@app.command()
def start(path: str, port: int = 8000, reload: bool = False):

    abs_path = os.path.abspath(path)
    deployements = _get_deployements()

    try:
        config_file_name = deployements[abs_path]
    except KeyError:
        typer.echo('No Quetz deployement found at {}.'.format(path))
        raise typer.Abort()

    config_file = os.path.join(abs_path, config_file_name)
    os.environ[_env_prefix + _env_config_file] = config_file
    os.chdir(path)

    import quetz
    quetz_src = os.path.dirname(quetz.__file__)
    uvicorn.run("quetz.main:app", reload=reload, reload_dirs=(quetz_src, ), port=port)


@app.command()
def run(path: str, 
        config_file_name: str = "config.toml", 
        create_conf: bool = False, 
        test: bool = False,
        port: int = 8000,
        reload: bool = False):

    abs_path = os.path.abspath(path)
    create(abs_path, config_file_name, create_conf, test)
    start(abs_path, port, reload)


@app.command()
def delete(path: str, force: bool = False):

    abs_path = os.path.abspath(path)
    deployements = _get_deployements()

    try:
        _ = deployements[abs_path]
    except KeyError:
        typer.echo('No Quetz deployement found at {}.'.format(path))
        raise typer.Abort()

    delete = force or typer.confirm("Delete Quetz deployement at {}?".format(path))
    if not delete:
        raise typer.Abort()

    shutil.rmtree(abs_path)
    _clean_deployements()


@app.command()
def list():
    deployements = _get_deployements()

    if len(deployements) > 0:
        typer.echo('\n'.join([p for p in deployements]))


if __name__ == "__main__":
    app()