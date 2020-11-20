import concurrent.futures
import inspect
import logging
from abc import abstractmethod
from typing import Optional

import requests
from fastapi import BackgroundTasks

from quetz import authorization
from quetz.config import Config
from quetz.dao import Dao

logger = logging.getLogger("quetz.tasks")


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

    def _execute_function(self, func, *args, **kwargs):

        resources = {
            "dao": self.dao,
            "auth": self.auth,
            "session": self.session,
            "config": self.config,
            "pkgstore": self.config.get_package_store(),
        }

        argnames = list(inspect.signature(func).parameters.keys())

        for arg, value in resources.items():
            if arg in argnames:
                kwargs[arg] = value

        self.background_tasks.add_task(
            func,
            *args,
            **kwargs,
        )


class SubprocessWorker(AbstractWorker):

    _executor: Optional[concurrent.futures.Executor] = None

    def __init__(self, api_key: str, browser_session: dict):

        if SubprocessWorker._executor is None:
            logger.debug("creating a new subprocess executor")
            SubprocessWorker._executor = concurrent.futures.ProcessPoolExecutor()
        self.api_key = api_key
        self.browser_session = browser_session

    @staticmethod
    def wrapper(func, api_key, browser_session, *args, **kwargs):

        import logging
        import os

        from quetz.authorization import Rules
        from quetz.config import Config, configure_logger
        from quetz.dao import Dao
        from quetz.database import get_session
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

        return func(
            *args,
            dao=dao,
            auth=auth,
            session=session,
            config=config,
            pkgstore=pkgstore,
            **kwargs,
        )

    def _execute_function(self, func, *args, **kwargs):
        self._executor.submit(
            self.wrapper, func, self.api_key, self.browser_session, *args, **kwargs
        )
