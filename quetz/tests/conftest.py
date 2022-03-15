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
def user_role():
    return None


@fixture
def user_without_profile(db, user_role):

    new_user = User(id=uuid.uuid4().bytes, username="bartosz", role=user_role)
    db.add(new_user)
    db.commit()

    yield new_user

    db.delete(new_user)
    db.commit()


@fixture
def user(db, user_without_profile):
    profile = Profile(
        name="Bartosz", avatar_url="http:///avatar", user=user_without_profile
    )
    db.add(profile)
    db.commit()

    yield user_without_profile

    db.query(Profile).filter(
        Profile.name == profile.name,
        Profile.avatar_url == profile.avatar_url,
        Profile.user_id == user_without_profile.id,
    ).delete()

    db.commit()
