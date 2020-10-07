# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.
from typing import Callable

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from sqlalchemy.pool import StaticPool

from quetz.db_models import Base


def get_engine(db_url, echo: bool = False, **kwargs) -> Engine:
    kwargs['echo'] = echo

    if db_url.startswith('sqlite'):
        kwargs.setdefault('connect_args', {'check_same_thread': False})

    if db_url.endswith(':memory:'):
        # If we're using an in-memory database, ensure that only one connection
        # is ever created.
        kwargs.setdefault('poolclass', StaticPool)

    engine = create_engine(db_url, **kwargs)
    Base.metadata.create_all(engine)
    return engine


def get_session_maker(engine) -> Callable[[], Session]:
    return sessionmaker(autocommit=False, autoflush=True, bind=engine)


def get_session(db_url, echo: bool = False, **kwargs) -> Session:
    return get_session_maker(get_engine(db_url, echo, **kwargs))()
