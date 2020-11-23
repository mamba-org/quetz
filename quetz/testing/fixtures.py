import os
import shutil
import tempfile

from fastapi.testclient import TestClient
from pytest import fixture

import quetz
from quetz.config import Config, get_plugin_manager
from quetz.dao import Dao
from quetz.database import get_engine, get_session_maker


@fixture
def plugin_manager():
    return get_plugin_manager()


@fixture
def sqlite_url():
    return "sqlite:///:memory:"


@fixture
def database_url(sqlite_url):
    db_url = os.environ.get("QUETZ_TEST_DATABASE", sqlite_url)
    return db_url


@fixture
def engine(config, plugin_manager, database_url):
    # we need to import the plugins before creating the db tables
    # because plugins make define some extra db models
    engine = get_engine(database_url, echo=False)
    yield engine
    engine.dispose()


@fixture
def session_maker(engine):

    # run the tests with a separate external DB transaction
    # so that we can easily rollback all db changes (even if commited)
    # done by the test client

    # Note: that won't work when rollback is explictly called in the implementation

    # see also: https://docs.sqlalchemy.org/en/13/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites # noqa

    connection = engine.connect()
    trans = connection.begin()
    yield get_session_maker(connection)
    trans.rollback()
    connection.close()


@fixture
def db(session_maker):

    session = session_maker()

    yield session

    session.close()


@fixture
def config_base(database_url):
    return f"""
[github]
# Register the app here: https://github.com/settings/applications/new
client_id = "aaa"
client_secret = "bbb"

[sqlalchemy]
database_url = "{database_url}"

[session]
secret = "eWrkA6xpa7LTSSYUwZEEVoOU62501Ucf9lmLcgzTj1I="
https_only = false
"""


@fixture
def config_extra():
    return ""


@fixture
def config_str(config_base, config_extra):
    return "\n".join([config_base, config_extra])


@fixture
def config_dir():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)


@fixture
def config(config_str, config_dir):

    config_path = os.path.join(config_dir, "config.toml")
    with open(config_path, "w") as fid:
        fid.write(config_str)
    old_dir = os.path.abspath(os.curdir)
    os.chdir(config_dir)
    os.environ["QUETZ_CONFIG_FILE"] = config_path
    data_dir = os.path.join(os.path.dirname(quetz.__file__), "tests", "data")
    for filename in os.listdir(data_dir):
        full_path = os.path.join(data_dir, filename)
        dest = os.path.join(config_dir, filename)
        if os.path.isfile(full_path):
            shutil.copy(full_path, dest)

    Config._instances = {}
    config = Config()
    yield config
    os.chdir(old_dir)


@fixture
def app(config, session_maker):
    from quetz.deps import get_db
    from quetz.main import app

    app.dependency_overrides[get_db] = lambda: session_maker()
    yield app
    app.dependency_overrides.pop(get_db)


@fixture
def client(app):
    client = TestClient(app)
    return client


@fixture
def dao(db) -> Dao:
    return Dao(db)
