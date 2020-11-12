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
def user_without_profile(db):

    new_user = User(id=uuid.uuid4().bytes, username="bartosz")
    db.add(new_user)
    db.commit()

    return new_user


@fixture
def user(db, user_without_profile):
    profile = Profile(
        name="Bartosz", avatar_url="http:///avatar", user=user_without_profile
    )
    db.add(profile)
    db.commit()
    yield user_without_profile
