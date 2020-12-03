import asyncio
import concurrent.futures
import inspect
import logging
import time
from abc import abstractmethod
from typing import Callable, Optional

import requests
from fastapi import BackgroundTasks

from quetz import authorization
from quetz.config import Config
from quetz.dao import Dao

try:
    import redis
    from rq import Queue

    rq_available = True
except ImportError:
    rq_available = False

logger = logging.getLogger("quetz.tasks")


def prepare_arguments(func: Callable, **resources):
    "select arguments for a function for resources based on its signature." ""

    # poorman's dependency injection pattern

    argnames = list(inspect.signature(func).parameters.keys())
    kwargs = {arg: value for arg, value in resources.items() if arg in argnames}

    return kwargs


def job_wrapper(func, api_key, browser_session, config, **kwargs):

    # database connections etc. are not serializable
    # so we need to recreate them in the process.
    # This allows us to manage database connectivity prior
    # to running a job.

    import logging
    import os

    from quetz.authorization import Rules
    from quetz.config import configure_logger
    from quetz.dao import Dao
    from quetz.database import get_session
    from quetz.deps import get_remote_session

    pkgstore = config.get_package_store()
    db = get_session(config.sqlalchemy_database_url)
    dao = Dao(db)
    auth = Rules(api_key, browser_session, db)
    session = get_remote_session()

    configure_logger(config)

    logger = logging.getLogger("quetz")
    logger.debug(
        f"evaluating function {func} in a subprocess task with pid {os.getpid()}"
    )

    extra_kwargs = prepare_arguments(
        func,
        dao=dao,
        auth=auth,
        session=session,
        config=config,
        pkgstore=pkgstore,
    )

    kwargs.update(extra_kwargs)

    func(**kwargs)


class AbstractWorker:
    @abstractmethod
    def execute(self, func, **kwargs):
        """execute function func on the worker."""

    @abstractmethod
    def wait(self):
        """wait for all jobs to finish"""


class ThreadingWorker(AbstractWorker):
    def __init__(
        self,
        background_tasks: BackgroundTasks,
        dao: Dao,
        auth: authorization.Rules,
        session: requests.Session,
        config: Config,
    ):
        self.dao = dao
        self.auth = auth
        self.background_tasks = background_tasks
        self.session = session
        self.config = config

    def execute(self, func: Callable, *args, **kwargs):

        resources = {
            "dao": self.dao,
            "auth": self.auth,
            "session": self.session,
            "config": self.config,
            "pkgstore": self.config.get_package_store(),
        }

        extra_kwargs = prepare_arguments(func, **resources)
        kwargs.update(extra_kwargs)

        self.background_tasks.add_task(
            func,
            **kwargs,
        )

    async def wait(self):
        await self.background_tasks()


class SubprocessWorker(AbstractWorker):

    _executor: Optional[concurrent.futures.Executor] = None

    def __init__(self, api_key: str, browser_session: dict, config: Config):

        if SubprocessWorker._executor is None:
            logger.debug("creating a new subprocess executor")
            SubprocessWorker._executor = concurrent.futures.ProcessPoolExecutor()
        self.api_key = api_key
        self.browser_session = browser_session
        self.config = config
        self.future = None

    def execute(self, func, *args, **kwargs):
        self.future = self._executor.submit(
            job_wrapper,
            func,
            self.api_key,
            self.browser_session,
            self.config,
            *args,
            **kwargs,
        )

    async def wait(self):
        loop = asyncio.get_event_loop()
        if self.future:
            return await loop.run_in_executor(None, self.future.result)


class RQManager(AbstractWorker):
    def __init__(
        self,
        host,
        port,
        db,
        api_key: str,
        browser_session: dict,
        config: Config,
        no_testing=True,
    ):
        self.host = host
        self.port = port
        self.db = db
        self.api_key = api_key
        self.browser_session = browser_session
        self.config = config
        self.conn = redis.StrictRedis(host=self.host, port=self.port, db=self.db)
        self.queue = Queue(connection=self.conn, is_async=no_testing)

    def execute(self, func, *args, **kwargs):
        self.job = self.queue.enqueue(
            job_wrapper,
            func,
            self.api_key,
            self.browser_session,
            self.config,
            *args,
            **kwargs,
        )

    # the function is blocking in nature and is declared
    # as 'async' so as to make redis-queue compatible
    # with the testing framework. It is not to be used otherwise.
    async def wait(self):
        while not self.job.is_finished:
            time.sleep(1)
        if self.job.result:
            return self.job.result
