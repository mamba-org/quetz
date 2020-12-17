# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.
import os
from typing import Callable

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from sqlalchemy.pool import Pool, StaticPool
from sqlalchemy.sql import expression
from sqlalchemy.types import Numeric

try:
    from sqlite3 import Connection as SQLiteConnection
except ImportError:
    SQLiteConnection = None
    print("Could not import sqlite3")


try:
    from psycopg2.extensions import connection as PGConnection
except ImportError:
    PGConnection = None
    print("Could not import postgres backend")


class version_match(expression.FunctionElement):
    type = Numeric()
    name = 'version_match'


@compiles(version_match, 'sqlite')
def sqlite_version_match(element, compiler, **kw):
    return compiler.visit_function(element)

pg_create_function = """\
CREATE OR REPLACE FUNCTION version_compare(varchar, varchar)
RETURNS boolean
AS '{libpath}'
LANGUAGE 'c'
"""

def load_plugins_after_connect(dbapi_connection, connection_record):
    if SQLiteConnection and type(dbapi_connection) is SQLiteConnection:
        # TODO
        if os.path.exist("PLUGIN_PATH"):
            dbapi_connection.enable_load_extension(True)
            dbapi_connection.load_extension("PLUGIN_PATH")
            dbapi_connection.enable_load_extension(False)
    elif PGConnection and type(dbapi_connection) is PGConnection:
        cursor = dbapi_connection.cursor()
        cursor.execute(pg_create_function.format(libpath="/db_ext/build/libquetz_pg.so"))
    print(dbapi_connection)
    print(type(dbapi_connection))

event.listen(Pool, 'first_connect', load_plugins_after_connect)
event.listen(StaticPool, 'first_connect', load_plugins_after_connect)


def get_engine(db_url, echo: bool = False, **kwargs) -> Engine:

    if db_url.startswith('sqlite'):
        kwargs.setdefault('connect_args', {'check_same_thread': False})

    if db_url.endswith(':memory:'):
        # If we're using an in-memory database, ensure that only one connection
        # is ever created.
        kwargs.setdefault('poolclass', StaticPool)

    engine = create_engine(db_url, echo=echo, **kwargs)
    return engine


def get_session_maker(engine) -> Callable[[], Session]:
    return sessionmaker(autocommit=False, autoflush=True, bind=engine)


def get_session(db_url, echo: bool = False, **kwargs) -> Session:
    return get_session_maker(get_engine(db_url, echo, **kwargs))()
