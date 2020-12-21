import logging
import os
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import Pool, StaticPool
from sqlalchemy.sql import expression
from sqlalchemy.types import Numeric

logger = logging.getLogger("quetz")

try:
    from sqlite3 import Connection as SQLiteConnection

    sqlite_available = True
except ImportError:
    sqlite_available = False
    print("Could not import sqlite3")


try:
    from psycopg2.extensions import connection as PGConnection

    postgres_available = True
except ImportError:
    postgres_available = False

    print("Could not import postgres backend")


pg_create_function = """\
CREATE OR REPLACE FUNCTION version_compare(varchar, varchar)
RETURNS boolean
AS '{libpath}'
LANGUAGE 'c'
"""

search_path = os.getenv("QUETZ_DATABASE_PLUGIN_PATH")

sqlite_plugin, pg_plugin = None, None
if search_path:
    plugin_path = Path(search_path)

    if (plugin_path / "libquetz_pg.so").exists():
        pg_plugin = str((plugin_path / "libquetz_pg.so").resolve())
        logger.info(
            "Looking for database extension: " "{plugin_path / 'libquetz_pg.so'}: FOUND"
        )
    else:
        logger.info(
            "Looking for database extension: "
            f"{plugin_path / 'libquetz_pg.so'}: NOT FOUND"
        )

    if (plugin_path / "libquetz_sqlite.so").exists():
        sqlite_plugin = str((plugin_path / "libquetz_sqlite.so").resolve())
        logger.info(
            "Looking for database extension: "
            f"{plugin_path / 'libquetz_sqlite.so'}: FOUND"
        )
    else:
        logger.info(
            "Looking for database extension: "
            f"{plugin_path / 'libquetz_sqlite.so'}: NOT FOUND"
        )


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
    if sqlite_available and type(dbapi_connection) is SQLiteConnection:
        if sqlite_plugin:
            dbapi_connection.enable_load_extension(True)
            dbapi_connection.load_extension(sqlite_plugin)
            dbapi_connection.enable_load_extension(False)
    elif postgres_available and type(dbapi_connection) is PGConnection:
        if pg_plugin:
            cursor = dbapi_connection.cursor()
            cursor.execute(pg_create_function.format(libpath=pg_plugin))


event.listen(Pool, 'first_connect', load_plugins_after_connect)
event.listen(StaticPool, 'first_connect', load_plugins_after_connect)
