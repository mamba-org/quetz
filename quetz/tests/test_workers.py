import pytest
import requests
from fastapi import BackgroundTasks

from quetz.authorization import Rules
from quetz.tasks.workers import ThreadingWorker


def basic_function():
    print("hello world!")


@pytest.fixture
def background_tasks():
    bg_tasks = BackgroundTasks()
    return bg_tasks


@pytest.fixture
def http_session():
    return requests.Session()


@pytest.fixture
def auth(db):
    session = {}
    api_key = "api-key"

    return Rules(api_key, session, db)


@pytest.mark.asyncio
async def test_run_action(capsys, background_tasks, dao, auth, http_session, config):

    worker = ThreadingWorker(background_tasks, dao, auth, http_session, config)
    worker._execute_function(basic_function)

    await background_tasks()

    captured = capsys.readouterr()
    assert captured.out == "hello world!\n"
