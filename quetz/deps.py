"""
Define common dependencies for fastapi depenendcy-injection system
"""

import requests
from fastapi import Depends, Request
from requests.adapters import HTTPAdapter
from sqlalchemy.orm import Session
from urllib3.util.retry import Retry

from quetz import authorization
from quetz.config import Config
from quetz.dao import Dao
from quetz.database import get_session as get_db_session

DEFAULT_TIMEOUT = 5  # seconds
MAX_RETRIES = 3


class TimeoutHTTPAdapter(HTTPAdapter):
    def __init__(self, *args, **kwargs):
        self.timeout = DEFAULT_TIMEOUT
        if "timeout" in kwargs:
            self.timeout = kwargs["timeout"]
            del kwargs["timeout"]
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        timeout = kwargs.get("timeout")
        if timeout is None:
            kwargs["timeout"] = self.timeout
        return super().send(request, **kwargs)


def get_config():
    config = Config()
    return config


def get_db(config: Config = Depends(get_config)):

    database_url = config.sqlalchemy_database_url
    db = get_db_session(database_url)
    try:
        yield db
    finally:
        db.close()


def get_dao(db: Session = Depends(get_db)):
    return Dao(db)


def get_session(request: Request):
    return request.session


def get_remote_session():
    session = requests.Session()
    retries = Retry(
        total=MAX_RETRIES, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
    )

    adapter = TimeoutHTTPAdapter(max_retries=retries)

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def get_rules(
    request: Request,
    session: dict = Depends(get_session),
    db: Session = Depends(get_db),
):
    return authorization.Rules(request.headers.get("x-api-key"), session, db)
