"""
Define common dependencies for fastapi depenendcy-injection system
"""

import requests
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from quetz import authorization
from quetz.config import Config
from quetz.dao import Dao
from quetz.database import get_session as get_db_session

config = Config()


def get_db():
    db = get_db_session(config.sqlalchemy_database_url)
    try:
        yield db
    finally:
        db.close()


def get_dao(db: Session = Depends(get_db)):
    return Dao(db)


def get_session(request: Request):
    return request.session


def get_remote_session():
    return requests.Session()


def get_rules(
    request: Request,
    session: dict = Depends(get_session),
    db: Session = Depends(get_db),
):
    return authorization.Rules(request.headers.get("x-api-key"), session, db)
