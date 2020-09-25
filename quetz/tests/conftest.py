"""py.test fixtures

Fixtures for Quetz components
-----------------------------
- `db`

"""
# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import os
import shutil
import tempfile
import uuid

from fastapi.testclient import TestClient
from pytest import fixture

from quetz.config import Config
from quetz.dao import Dao
from quetz.database import get_engine, get_session_maker
from quetz.db_models import Profile, User


@fixture
def session_maker():
    engine = get_engine('sqlite:///:memory:')
    yield get_session_maker(engine)
    engine.dispose()


@fixture
def db(session_maker):
    session = session_maker()
    yield session
    session.rollback()
    session.close()


@fixture
def user(db):
    user = User(id=uuid.uuid4().bytes, username="bartosz")
    profile = Profile(name="Bartosz", avatar_url="http:///avatar", user=user)
    db.add(user)
    db.add(profile)
    db.commit()
    yield user
    db.delete(profile)
    db.delete(user)
    db.commit()


@fixture
def config():

    config_str = r"""
[github]
# Register the app here: https://github.com/settings/applications/new
client_id = "aaa"
client_secret = ""

[sqlalchemy]
database_url = "sqlite:///:memory:"

[session]
secret = "eWrkA6xpa7LTSSYUwZEEVoOU62501Ucf9lmLcgzTj1I="
https_only = false
"""

    path = tempfile.mkdtemp()
    config_path = os.path.join(path, "config.toml")
    with open(config_path, "w") as fid:
        fid.write(config_str)
    old_dir = os.path.abspath(os.curdir)
    os.chdir(path)
    os.environ["QUETZ_CONFIG_FILE"] = config_path
    shutil.copyfile(
        os.path.join(old_dir, "quetz", "tests", "data", "test-package-0.1-0.tar.bz2"),
        os.path.join(path, "test-package-0.1-0.tar.bz2"),
    )
    config = Config()
    yield config
    os.chdir(old_dir)


@fixture
def app(config, session_maker):
    from quetz.main import app, get_db

    app.dependency_overrides[get_db] = lambda: session_maker()
    return app


@fixture
def client(app):
    client = TestClient(app)
    return client


@fixture
def dao(db) -> Dao:
    return Dao(db)
