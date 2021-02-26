import os
import socket
from contextlib import closing

import pytest
import requests
from fastapi import BackgroundTasks

from quetz.authorization import Rules
from quetz.dao import Dao
from quetz.db_models import User
from quetz.tasks.workers import RQManager, SubprocessWorker, ThreadingWorker


@pytest.fixture
def sqlite_url(config_dir):
    # overriding sqlite_url to save to file so that
    # we can access the same db from a sub-process
    return f'sqlite:///{config_dir}/quetz.db'


@pytest.fixture
def http_session():
    return requests.Session()


@pytest.fixture
def background_tasks():
    bg_tasks = BackgroundTasks()
    return bg_tasks


@pytest.fixture
def api_key():
    return "api-key"


@pytest.fixture
def browser_session():
    return {}


@pytest.fixture
def auth(db, api_key, browser_session):
    return Rules(api_key, browser_session, db)


@pytest.fixture
def redis_ip():
    return "127.0.0.1"


@pytest.fixture
def redis_port():
    return 6379


@pytest.fixture
def redis_db():
    return 0


@pytest.fixture
def threading_worker(config):
    worker = ThreadingWorker(config)
    return worker


@pytest.fixture
def subprocess_worker(api_key, browser_session, db, config):
    SubprocessWorker._executor = None
    worker = SubprocessWorker(config)
    return worker


@pytest.fixture
def redis_worker(redis_ip, redis_port, redis_db, api_key, browser_session, db, config):
    worker = RQManager(
        redis_ip,
        redis_port,
        redis_db,
        config,
        no_testing=False,
    )
    return worker


def check_socket(host, port):
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.settimeout(2)
        if sock.connect_ex((host, port)) == 0:
            return True
        else:
            return False


def check_redis():
    return check_socket('127.0.0.1', 6379)


@pytest.fixture(
    params=[
        "threading_worker",
        "subprocess_worker",
        pytest.param(  # type: ignore
            "redis_worker",
            marks=pytest.mark.skipif(not check_redis(), reason='no redis'),
        ),
    ]
)
def any_worker(request):
    val = request.getfixturevalue(request.param)
    return val


def basic_function(config_dir):
    os.chdir(config_dir)
    with open("test.txt", "w") as fid:
        fid.write("hello world!")


def function_with_dao(dao: Dao):
    dao.create_user_with_role("my-user")


@pytest.fixture
def db_cleanup(config):

    # we can't use the db fixture for cleaning up because
    # it automatically rollsback all operations

    yield

    from quetz.database import get_session

    db = get_session(config.sqlalchemy_database_url)
    user = db.query(User).one_or_none()
    if user:
        db.delete(user)
        db.commit()


@pytest.mark.asyncio
async def test_threading_worker_execute(background_tasks, any_worker, db, config_dir):

    any_worker.execute(basic_function, config_dir=config_dir)

    await any_worker.wait()

    with open("test.txt") as fid:
        output = fid.read()

    assert output == "hello world!"


@pytest.mark.asyncio
async def test_threading_worker_execute_with_dao(
    background_tasks, any_worker, db, db_cleanup
):

    any_worker.execute(function_with_dao)

    await any_worker.wait()

    users = db.query(User).all()

    assert len(users) == 1
    assert users[0].username == 'my-user'

    # we need to explicitly cleanup because sub-process did not use
    # our db fixture, this will be done at teardown in the db_cleanup fixture
