import pytest
import requests
from fastapi import BackgroundTasks

from quetz.authorization import Rules
from quetz.dao import Dao
from quetz.db_models import User
from quetz.tasks.workers import SubprocessWorker, ThreadingWorker


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
def threading_worker(background_tasks, dao, auth, http_session, config):
    worker = ThreadingWorker(background_tasks, dao, auth, http_session, config)
    return worker


@pytest.fixture
def subprocess_worker(api_key, browser_session, db, config):
    SubprocessWorker._executor = None
    worker = SubprocessWorker(api_key, browser_session)
    return worker


@pytest.fixture(params=["threading_worker", "subprocess_worker"])
def any_worker(request):
    val = request.getfixturevalue(request.param)
    return val


def basic_function():
    with open("test.txt", "w") as fid:
        fid.write("hello world!")


def function_with_dao(dao: Dao):
    dao.create_user_with_role("my-user")


@pytest.mark.asyncio
async def test_threading_worker_execute(background_tasks, any_worker, db):

    any_worker.execute(basic_function)

    await any_worker.wait()

    with open("test.txt") as fid:
        output = fid.read()

    assert output == "hello world!"


@pytest.mark.asyncio
async def test_threading_worker_execute_with_dao(background_tasks, any_worker, db):

    any_worker.execute(function_with_dao)

    await any_worker.wait()

    users = db.query(User).all()

    assert len(users) == 1
    assert users[0].username == 'my-user'
