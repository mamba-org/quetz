import inspect
import logging
from abc import abstractmethod

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
