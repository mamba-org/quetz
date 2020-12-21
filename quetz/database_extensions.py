import logging
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import Pool, StaticPool
from sqlalchemy.sql import expression
from sqlalchemy.types import Numeric

from quetz.config import Config, configure_logger

config = Config()
logger = logging.getLogger("quetz")
configure_logger(loggers=("quetz",))

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


pg_create_function = """\
CREATE OR REPLACE FUNCTION version_compare(varchar, varchar)
RETURNS boolean
AS '{libpath}'
LANGUAGE 'c'
"""

sqlite_plugin, pg_plugin = None, None
if config.sqlalchemy_database_plugin_path:
    plugin_path = Path(config.sqlalchemy_database_plugin_path)
    logger.info(f"Looking for database extension: {plugin_path / 'libquetz_pg.so'}")

    if (plugin_path / "libquetz_pg.so").exists():
        pg_plugin = str((plugin_path / "libquetz_pg.so").resolve())

    logger.info(f"Looking for database extension: {plugin_path / 'libquetz_sqlite.so'}")
    if (plugin_path / "libquetz_sqlite.so").exists():
        sqlite_plugin = str((plugin_path / "libquetz_sqlite.so").resolve())


class _version_match(expression.FunctionElement):
    type = Numeric()
    name = 'version_match'


@compiles(_version_match, 'sqlite')
def sqlite_version_match(element, compiler, **kw):
    return compiler.visit_function(element)


if not sqlite_plugin and not pg_plugin:
    version_match = None
else:
    version_match = _version_match


def load_plugins_after_connect(dbapi_connection, connection_record):
    if SQLiteConnection and type(dbapi_connection) is SQLiteConnection:
        if sqlite_plugin:
            dbapi_connection.enable_load_extension(True)
            dbapi_connection.load_extension(sqlite_plugin)
            dbapi_connection.enable_load_extension(False)
    elif PGConnection and type(dbapi_connection) is PGConnection:
        if pg_plugin:
            cursor = dbapi_connection.cursor()
            cursor.execute(pg_create_function.format(libpath=pg_plugin))


event.listen(Pool, 'first_connect', load_plugins_after_connect)
event.listen(StaticPool, 'first_connect', load_plugins_after_connect)
