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

    db.delete(profile)
    db.commit()


@fixture
def auth_client(client, user):
    """authenticated client"""
    response = client.get(f"/api/dummylogin/{user.username}")
    assert response.status_code == 200
    return client
