import uuid

import pytest
from sqlalchemy import event

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


@pytest.fixture
def db(session_maker, expires_on_commit, auto_rollback, request):
    session = session_maker()

    # We overwrite this fixture to support rollbacks within
    # the test by wrapping the test in a nested transaction.
    # We start a new nested transaction when a transaction
    # ends using the `after_transaction_end` event.
    # See https://docs.sqlalchemy.org/en/13/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites # noqa
    # for why this is necessary and how this works.

    if auto_rollback:
        session.begin_nested()

        # each time the nested transaction ends, reopen it
        @event.listens_for(session, "after_transaction_end")
        def restart_savepoint(session, transaction):
            if transaction.nested and not transaction._parent.nested:
                session.expire_all()
                session.begin_nested()

    session.expire_on_commit = expires_on_commit
    yield session
    session.close()
