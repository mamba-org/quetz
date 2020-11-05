"""py.test fixtures

Fixtures for Quetz components
-----------------------------
- `db`

"""
# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.


import uuid

from pytest import fixture

from quetz.db_models import Profile, User

pytest_plugins = "quetz.testing.fixtures"


@fixture
def user(db):
    user = User(id=uuid.uuid4().bytes, username="bartosz")
    profile = Profile(name="Bartosz", avatar_url="http:///avatar", user=user)
    db.add(user)
    db.add(profile)
    db.commit()
    yield user
