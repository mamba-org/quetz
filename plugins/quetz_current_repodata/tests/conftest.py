import uuid

from pytest import fixture

from quetz import rest_models
from quetz.dao import Dao
from quetz.db_models import Profile, User

pytest_plugins = "quetz.testing.fixtures"


@fixture
def dao(db) -> Dao:
    return Dao(db)


@fixture
def user(db):
    user = User(id=uuid.uuid4().bytes, username="madhurt")
    db.add(user)
    db.commit()
    yield user


@fixture
def profile(db, user):
    user_profile = Profile(
        name="madhur", avatar_url="madhur-tandon", user_id=user.id, user=user
    )
    db.add(user_profile)
    db.commit()
    yield user


@fixture
def channel(dao, user, db):
    channel_data = rest_models.Channel(
        name="test-channel",
        private=False,
    )

    channel = dao.create_channel(channel_data, user.id, "owner")

    yield channel

    db.delete(channel)
    db.commit()


@fixture
def subdirs():
    return ["linux-64"]


@fixture
def files():
    return {"linux-64": []}


@fixture
def packages():
    return {"linux-64": []}
