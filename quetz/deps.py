"""
Define common dependencies for fastapi depenendcy-injection system
"""

import logging

import requests
from fastapi import BackgroundTasks, Depends, HTTPException, Request, status
from requests.adapters import HTTPAdapter
from sqlalchemy.orm import Session
from urllib3.util.retry import Retry

from quetz import authorization, db_models
from quetz.config import Config
from quetz.dao import Dao
from quetz.database import get_session as get_db_session
from quetz.tasks.common import Task

DEFAULT_TIMEOUT = 5  # seconds
MAX_RETRIES = 3

logger = logging.getLogger("quetz")


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
    db = get_db_session(database_url, echo=config.sqlalchemy_echo_sql)
    try:
        yield db
    finally:
        db.close()


def get_dao(db: Session = Depends(get_db)):
    return Dao(db)


def get_session(request: Request):
    return request.session


def get_remote_session() -> requests.Session:
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


def get_tasks_worker(
    background_tasks: BackgroundTasks,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
    session: requests.Session = Depends(get_remote_session),
    config: Config = Depends(get_config),
) -> Task:

    return Task(auth, dao.db)


class ChannelChecker:
    def __init__(
        self,
        allow_proxy: bool = False,
        allow_mirror: bool = False,
        allow_local: bool = True,
    ):
        self.allow_proxy = allow_proxy
        self.allow_mirror = allow_mirror
        self.allow_local = allow_local

    def __call__(
        self,
        channel_name: str,
        dao: Dao = Depends(get_dao),
        auth: authorization.Rules = Depends(get_rules),
    ) -> db_models.Channel:
        channel = dao.get_channel(channel_name.lower())

        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Channel {channel_name} not found",
            )

        auth.assert_channel_read(channel)

        mirror_url = channel.mirror_channel_url

        is_proxy = mirror_url and channel.mirror_mode == "proxy"
        is_mirror = mirror_url and channel.mirror_mode == "mirror"
        is_local = not mirror_url
        if is_proxy and not self.allow_proxy:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail="This method is not implemented for proxy channels",
            )
        if is_mirror and not self.allow_mirror:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail="This method is not implemented for mirror channels",
            )
        if is_local and not self.allow_local:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail="This method is not implemented for local channels",
            )
        return channel


get_channel_or_fail = ChannelChecker(allow_proxy=False, allow_mirror=True)
get_channel_allow_proxy = ChannelChecker(allow_proxy=True, allow_mirror=True)
get_channel_mirror_only = ChannelChecker(allow_mirror=True, allow_local=False)


def get_package_or_fail(
    package_name: str,
    channel_name: str,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
) -> db_models.Package:

    package = dao.get_package(channel_name.lower(), package_name)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Package {channel_name}/{package_name} not found",
        )

    auth.assert_package_read(package)
    return package
