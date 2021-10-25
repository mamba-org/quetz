# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.
import logging
from contextlib import contextmanager
from typing import Callable

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from sqlalchemy.pool import StaticPool

from quetz.config import Config
from quetz.metrics.middleware import DATABASE_CONNECTIONS_USED, DATABASE_POOL_SIZE

engine = None

logger = logging.getLogger("quetz")


def set_metrics(*args):
    checked_in = engine.pool.checkedin()
    checked_out = engine.pool.checkedout()
    pool_size = checked_in + checked_out
    DATABASE_POOL_SIZE.set(pool_size)
    DATABASE_CONNECTIONS_USED.set(checked_out)


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
                db_url, echo=echo, pool_size=200, max_overflow=100, **kwargs
            )
            for event_name in ['connect', 'close', 'checkin', 'checkout']:
                event.listen(engine, event_name, set_metrics)
        else:
            engine = create_engine(db_url, echo=echo, **kwargs)

        def on_connect(dbapi_conn, conn_record):
            logger.debug("connection opened: %s", engine.pool.status())

        def on_close(dbapi_conn, conn_record):
            logger.debug("connection closed: %s", engine.pool.status())

        event.listen(engine, 'connect', on_connect)
        event.listen(engine, 'close', on_close)

    return engine


def get_session_maker(engine) -> Callable[[], Session]:
    return sessionmaker(autocommit=False, autoflush=True, bind=engine)


def get_session(db_url: str, echo: bool = False, **kwargs) -> Session:
    """Get a database session.

    Important note: this function is mocked during tests!

    """
    return get_session_maker(get_engine(db_url, echo, **kwargs))()


@contextmanager
def get_db_manager():
    config = Config()
    database_url = config.sqlalchemy_database_url
    db = get_session(database_url, echo=config.sqlalchemy_echo_sql)

    try:
        yield db
    finally:
        db.close()
