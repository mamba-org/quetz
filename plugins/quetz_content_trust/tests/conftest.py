import uuid

from pytest import fixture
from quetz_content_trust import db_models

from quetz import rest_models
from quetz.dao import Dao
from quetz.db_models import User

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
def reposigning_private_key(db, user, channel):
    rs_key = db_models.RepodataSigningKey(
        private_key="f3cdab14740066fb277651ec4f96b9f6c3e3eb3f812269797b9656074cd52133",
        channel_name=channel.name,
        user_id=user.id,
    )

    db.add(rs_key)
    db.commit()

    yield rs_key

    db.delete(rs_key)
    db.commit()
