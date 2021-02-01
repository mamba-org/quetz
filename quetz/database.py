# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.
import logging
from typing import Callable

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from sqlalchemy.pool import StaticPool

from quetz.metrics.middleware import DATABASE_CONNECTIONS_USED, DATABASE_POOL_SIZE

engine = None

logger = logging.getLogger("quetz")


def get_engine(db_url, echo: bool = False, reuse_engine=True, **kwargs) -> Engine:

    if db_url.startswith('sqlite'):
        kwargs.setdefault('connect_args', {'check_same_thread': False})

    if db_url.endswith(':memory:'):
        # If we're using an in-memory database, ensure that only one connection
        # is ever created.
        kwargs.setdefault('poolclass', StaticPool)

    global engine

    if not engine or not reuse_engine:
        # TODO make configurable!
        if db_url.startswith('postgres'):
            engine = create_engine(
                db_url, echo=echo, pool_size=32, max_overflow=100, **kwargs
            )
        else:
            engine = create_engine(db_url, echo=echo, **kwargs)

        def on_connect(dbapi_conn, conn_record):
            logger.debug("connection opened: %s", engine.pool.status())

        def on_close(dbapi_conn, conn_record):
            logger.debug("connection closed: %s", engine.pool.status())

        def set_metrics(*args):
            checked_in = engine.pool.checkedin()
            checked_out = engine.pool.checkedout()
            pool_size = checked_in + checked_out
            DATABASE_POOL_SIZE.set(pool_size)
            DATABASE_CONNECTIONS_USED.set(checked_out)

        event.listen(engine, 'connect', on_connect)
        event.listen(engine, 'close', on_close)
        event.listen(engine, 'connect', set_metrics)
        event.listen(engine, 'close', set_metrics)
        event.listen(engine, 'checkout', set_metrics)
        event.listen(engine, 'checkin', set_metrics)

    return engine


def get_session_maker(engine) -> Callable[[], Session]:
    return sessionmaker(autocommit=False, autoflush=True, bind=engine)


def get_session(db_url, echo: bool = False, **kwargs) -> Session:
    return get_session_maker(get_engine(db_url, echo, **kwargs))()
