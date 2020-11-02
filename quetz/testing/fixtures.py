import os
import shutil
import tempfile

from fastapi.testclient import TestClient
from pytest import fixture

from quetz.config import Config
from quetz.database import get_engine, get_session_maker


@fixture
def engine():
    db_url = os.environ.get("QUETZ_TEST_DATABASE", 'sqlite:///:memory:')
    engine = get_engine(db_url)
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
    data_dir = os.path.join(old_dir, "quetz", "tests", "data")
    for filename in os.listdir(data_dir):
        full_path = os.path.join(data_dir, filename)
        dest = os.path.join(path, filename)
        if os.path.isfile(full_path):
            shutil.copy(full_path, dest)
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
