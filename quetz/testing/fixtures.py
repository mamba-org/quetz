import os
import shutil
import tempfile
from typing import List

from alembic.command import upgrade as alembic_upgrade
from fastapi.testclient import TestClient
from pytest import fixture

import quetz
from quetz.cli import _alembic_config
from quetz.config import Config
from quetz.dao import Dao
from quetz.database import get_engine, get_session_maker
from quetz.db_models import Base


@fixture
def sqlite_in_memory():
    """whether to create a sqlite DB in memory or on the filesystem."""
    return True


@fixture
def sqlite_url(sqlite_in_memory):
    if sqlite_in_memory:
        yield "sqlite:///:memory:"
    else:
        try:
            sql_path = tempfile.TemporaryDirectory()
            yield f"sqlite:///{sql_path.name}/test_quetz.sqlite"
        finally:
            sql_path.cleanup()


@fixture
def database_url(sqlite_url):
    db_url = os.environ.get("QUETZ_TEST_DATABASE", sqlite_url)
    return db_url


@fixture
def sql_echo():
    """whether to activate SQL echo during the tests or not."""
    return False


@fixture
def engine(database_url, sql_echo):
    sql_echo = bool(os.environ.get("QUETZ_TEST_ECHO_SQL", sql_echo))
    engine = get_engine(database_url, echo=sql_echo, reuse_engine=False)
    yield engine
    engine.dispose()


@fixture
def use_migrations() -> bool:
    USE_MIGRATIONS = "use-migrations"
    CREATE_TABLES = "create-tables"
    migrations_env = os.environ.get("QUETZ_TEST_DBINIT", CREATE_TABLES)
    if migrations_env.lower() == CREATE_TABLES:
        return False
    elif migrations_env.lower() == USE_MIGRATIONS:
        return True
    else:
        raise ValueError(
            f"QUETZ_TEST_DBINIT should be either {CREATE_TABLES} or {USE_MIGRATIONS}"
        )


@fixture
def sql_connection(engine):
    connection = engine.connect()
    yield connection
    connection.close()


@fixture
def alembic_config(database_url, sql_connection):
    alembic_config = _alembic_config(database_url)
    alembic_config.attributes["connection"] = sql_connection
    return alembic_config


@fixture
def create_tables(alembic_config, engine, use_migrations):

    if use_migrations:
        alembic_upgrade(alembic_config, 'heads', sql=False)
    else:
        Base.metadata.create_all(engine)


@fixture
def auto_rollback():
    """Whether to revert automatically the changes in the database after each test.

    In most cases, you will want to set this flag to True, only sporadically you might
    run the tests outside a revertible transaction (for example, to test interaction
    between two concurrent clients). But then you will need to clean up the db objects
    manually after each test. Use with care.

    See also the comment in session_maker fixture."""

    return True


@fixture
def session_maker(sql_connection, create_tables, auto_rollback):

    # run the tests with a separate external DB transaction
    # so that we can easily rollback all db changes (even if commited)
    # done by the test client

    # Note: when rollback is explictly called in the implementation,
    #       it will remove all objects created in the test even the ones
    #       that were already committed!

    # see also: https://docs.sqlalchemy.org/en/13/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites # noqa

    if auto_rollback:
        trans = sql_connection.begin()

    sql_connection.name = 'sqlite-test'
    yield get_session_maker(sql_connection)

    if auto_rollback:
        trans.rollback()


@fixture
def expires_on_commit():
    return True


@fixture
def db(session_maker, expires_on_commit):
    session = session_maker()
    session.expire_on_commit = expires_on_commit
    yield session
    session.close()


@fixture
def config_auth():
    return """
[github]
# Register the app here: https://github.com/settings/applications/new
client_id = "aaa"
client_secret = "bbb"
"""


@fixture
def config_base(database_url, plugins, config_auth):
    return f"""
{config_auth}

[sqlalchemy]
database_url = "{database_url}"

[session]
secret = "eWrkA6xpa7LTSSYUwZEEVoOU62501Ucf9lmLcgzTj1I="
https_only = false

[plugins]
enabled = {plugins}
"""


@fixture
def config_extra():
    return ""


@fixture
def config_str(config_base, config_extra):
    return "\n".join([config_base, config_extra])


@fixture
def home():
    return os.path.abspath(os.path.curdir)


@fixture
def config_dir(home):
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)


@fixture(scope="session")
def test_data_dir():
    return os.path.join(os.path.dirname(quetz.__file__), "tests", "data")


@fixture
def config(config_str, config_dir, test_data_dir):

    config_path = os.path.join(config_dir, "config.toml")
    with open(config_path, "w") as fid:
        fid.write(config_str)
    old_dir = os.path.abspath(os.curdir)
    os.chdir(config_dir)
    os.environ["QUETZ_CONFIG_FILE"] = config_path
    for filename in os.listdir(test_data_dir):
        full_path = os.path.join(test_data_dir, filename)
        dest = os.path.join(config_dir, filename)
        if os.path.isfile(full_path):
            shutil.copy(full_path, dest)

    Config._instances = {}
    config = Config()
    yield config
    del os.environ["QUETZ_CONFIG_FILE"]
    Config._instances = {}
    os.chdir(old_dir)


@fixture
def plugins() -> List[str]:
    return []


@fixture
def app(config, db, mocker):

    # frontend router catches all urls
    # and takes priority over routes added after (in tests)
    # so we avoid adding it here
    mocker.patch("quetz.frontend.register")

    from quetz.deps import get_db
    from quetz.main import app

    # mocking is required for some functions that do not use fastapi
    # dependency injection (mainly non-request functions)
    def get_session_mock(*args, **kwargs):
        return db

    mocker.patch("quetz.database.get_session", get_session_mock)

    # overiding dependency works with all requests handlers that
    # depend on quetz.deps.get_db
    app.dependency_overrides[get_db] = lambda: db

    # root url was removed with fronted urls above but
    # redirects to root must work for some tests to pass
    @app.get("/")
    def root_endpoint():
        return "root"

    yield app
    app.dependency_overrides.pop(get_db)


@fixture
def client(app):
    client = TestClient(app)
    return client


@fixture
def auth_client(client, user):
    """authenticated client"""
    response = client.get(f"/api/dummylogin/{user.username}")
    assert response.status_code == 200
    return client


@fixture
def dao(db) -> Dao:
    return Dao(db)
