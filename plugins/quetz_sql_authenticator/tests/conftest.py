import uuid

import pytest

from quetz.authorization import SERVER_MEMBER, SERVER_OWNER
from quetz.db_models import Profile, User

pytest_plugins = "quetz.testing.fixtures"


@pytest.fixture
def plugins():
    return ["quetz-sql-authenticator"]


@pytest.fixture
def testuser():
    return "testuser"


@pytest.fixture
def testpassword():
    return "testpassword"


# Fixture taken from the pytest_harvester plugin
@pytest.fixture
def owner_role():
    return SERVER_OWNER


@pytest.fixture
def member_role():
    return SERVER_MEMBER


@pytest.fixture
def owner_user(db, owner_role):
    yield _create_user(db, owner_role, "test_owner")
    _delete_user(db, "test_owner")


@pytest.fixture
def member_user(db, member_role):
    yield _create_user(db, member_role, "test_member")
    _delete_user(db, "test_member")


@pytest.fixture
def owner_client(client, owner_user):
    return _create_auth_client(client, owner_user)


@pytest.fixture
def member_client(client, member_user):
    return _create_auth_client(client, member_user)


def _create_auth_client(client, user):
    """authenticated client"""
    response = client.get(f"/api/dummylogin/{user.username}")
    assert response.status_code == 200
    return client


def _create_user(db, user_role, username):
    new_user = User(id=uuid.uuid4().bytes, username=username, role=user_role)
    profile = Profile(name=username, avatar_url="http:///avatar", user=new_user)
    db.add(profile)
    db.add(new_user)
    db.commit()

    return new_user


def _delete_user(db, username):
    user = db.query(User).filter(User.username == username).one()
    db.delete(user)
    db.commit()
