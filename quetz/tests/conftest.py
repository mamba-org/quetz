"""py.test fixtures

Fixtures for Quetz components
-----------------------------
- `db`

"""
# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import os
import tempfile

from fastapi.testclient import TestClient
from pytest import fixture
from sqlalchemy import MetaData

from quetz.database import get_session

# global db session object
_db = None


@fixture
def db():
    """Get a db session"""
    global _db
    if _db is None:
        _db = get_session('sqlite:///:memory:')

    return _db


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
    old_dir = os.curdir
    os.chdir(path)
    os.environ["QUETZ_CONFIG_FILE"] = config_path
    yield config_path
    os.chdir(old_dir)


@fixture
def app(config, db):
    from quetz.main import app, get_db

    app.dependency_overrides[get_db] = lambda: db
    return app


@fixture
def client(app):
    client = TestClient(app)
    return client


def clear_all(db):
    engine = db.get_bind()
    meta = MetaData(bind=engine, reflect=True)
    for table in reversed(meta.sorted_tables):
        db.execute(table.delete())
    db.commit()
