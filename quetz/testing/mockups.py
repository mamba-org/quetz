import pickle
from typing import Callable, Optional, Union

import requests

from quetz.config import Config
from quetz.dao import Dao
from quetz.tasks.workers import job_wrapper, prepare_arguments


class TestWorker:
    "synchronous worker for testing"

    def __init__(
        self,
        config: Config,
        db,
        dao: Dao,
        session: Optional[requests.Session] = None,
    ):
        self.db = db
        self.dao = dao
        self.session = session
        self.config = config

    def execute(self, func: Union[Callable, bytes], *args, **kwargs):

        resources = {
            "db": self.db,
            "dao": self.dao,
            "pkgstore": self.config.get_package_store(),
        }

        if self.session:
            resources['session'] = self.session

        if isinstance(func, bytes):
            callable_func = pickle.loads(func)
        else:
            callable_func = func

        extra_kwargs = prepare_arguments(callable_func, **resources)
        kwargs.update(extra_kwargs)
        job_wrapper(func, self.config, *args, **kwargs)
