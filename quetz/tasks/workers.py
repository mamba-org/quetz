import asyncio
import concurrent.futures
import inspect
import logging
from abc import abstractmethod
from typing import Callable, Optional

import requests
from fastapi import BackgroundTasks

from quetz import authorization
from quetz.config import Config
from quetz.dao import Dao

logger = logging.getLogger("quetz.tasks")


def prepare_arguments(func: Callable, **resources):

    argnames = list(inspect.signature(func).parameters.keys())
    kwargs = {arg: value for arg, value in resources.items() if arg in argnames}

    return kwargs


class AbstractWorker:
    @abstractmethod
    def _execute_function(self, func, *args, **kwargs):
        ...


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

    def _execute_function(self, func: Callable, *args, **kwargs):

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
            *args,
            **kwargs,
        )

    async def wait(self):
        await self.background_tasks()


class SubprocessWorker(AbstractWorker):

    _executor: Optional[concurrent.futures.Executor] = None

    def __init__(self, api_key: str, browser_session: dict):

        if SubprocessWorker._executor is None:
            logger.debug("creating a new subprocess executor")
            SubprocessWorker._executor = concurrent.futures.ProcessPoolExecutor()
        self.api_key = api_key
        self.browser_session = browser_session
        self.future = None

    @staticmethod
    def wrapper(func, api_key, browser_session, *args, **kwargs):

        import logging
        import os

        from quetz.authorization import Rules
        from quetz.config import Config, configure_logger
        from quetz.dao import Dao
        from quetz.database import get_session
        from quetz.db_models import User
        from quetz.deps import get_remote_session

        config = Config()
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

        func(
            *args,
            **kwargs,
        )

        return db.query(User).all()

    def _execute_function(self, func, *args, **kwargs):
        self.future = self._executor.submit(
            self.wrapper, func, self.api_key, self.browser_session, *args, **kwargs
        )

    async def wait(self):
        loop = asyncio.get_event_loop()
        if self.future:
            return await loop.run_in_executor(None, self.future.result)
