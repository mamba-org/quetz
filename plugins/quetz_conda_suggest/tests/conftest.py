import json
import uuid

from pytest import fixture
from quetz_conda_suggest import db_models

from quetz import rest_models
from quetz.dao import Dao
from quetz.db_models import User, Profile

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
    user_profile = Profile(name="madhur", avatar_url="madhur-tandon", user_id=user.id, user=user)
    db.add(user_profile)
    db.commit()
    yield user


@fixture
def channel(dao, user, db):
    channel_data = rest_models.Channel(
        name="test_channel",
        private=False,
    )

    channel = dao.create_channel(channel_data, user.id, "owner")

    yield channel

    db.delete(channel)
    db.commit()


@fixture
def package(dao, user, channel, db):
    new_package_data = rest_models.Package(name="test-package")

    package = dao.create_package(
        channel.name,
        new_package_data,
        user_id=user.id,
        role="owner",
    )

    yield package

    db.delete(package)
    db.commit()


@fixture
def package_version(user, channel, db, dao, package):
    package_format = 'tarbz2'
    package_info = '{"size": 5000, "subdir": "linux-64"}'

    version = dao.create_version(
        channel.name,
        package.name,
        package_format,
        "linux-64",
        "0.1",
        "0",
        "0",
        "test-package-0.1-0.tar.bz2",
        package_info,
        user.id,
        size=0,
    )

    yield version

    db.delete(version)
    db.commit()


@fixture
def subdir():
    return "linux-64"


@fixture
def package_conda_suggest(package_version, db):
    meta = db_models.CondaSuggestMetadata(
        version_id=package_version.id,
        data=json.dumps({"test-bin": "test-package"}),
    )

    db.add(meta)
    db.commit()

    yield meta

    db.delete(meta)
    db.commit()
