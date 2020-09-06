"""py.test fixtures

Fixtures for Quetz components
-----------------------------
- `db`

"""
# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from pytest import fixture

from quetz.database import get_session

# global db session object
_db = None


@fixture
def db():
    """Get a db session"""
    global _db
    if _db is None:
        _db = get_session('sqlite:///:memory:')

    return _db
