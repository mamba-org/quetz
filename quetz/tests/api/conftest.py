import uuid

import pytest

from quetz.dao import Dao
from quetz.db_models import Profile, User
from quetz.rest_models import Channel, Package


@pytest.fixture
def package_name():
    return "my-package"


@pytest.fixture
def channel_name():
    return "my-channel"


@pytest.fixture
def private_channel(dao, other_user, channel_role):

    channel_name = "private-channel"

    channel_data = Channel(name=channel_name, private=True)
    channel = dao.create_channel(channel_data, other_user.id, "owner")

    return channel


@pytest.fixture
def private_package(dao, other_user, private_channel):

    package_name = "private-package"
    package_data = Package(name=package_name)
    package = dao.create_package(
        private_channel.name, package_data, other_user.id, "owner"
    )

    return package


@pytest.fixture
def private_package_version(dao, private_channel, private_package, other_user):
    package_format = "tarbz2"
    package_info = "{}"
    version = dao.create_version(
        private_channel.name,
        private_package.name,
        package_format,
        "linux-64",
        "0.1",
        "0",
        "",
        "",
        package_info,
        other_user.id,
    )

    return version


@pytest.fixture
def package_version(db, user, channel_name, package_name, dao: Dao):
    channel_data = Channel(name=channel_name, private=False)
    package_data = Package(name=package_name)

    channel = dao.create_channel(channel_data, user.id, "owner")
    package = dao.create_package(channel_name, package_data, user.id, "owner")
    package_format = "tarbz2"
    package_info = "{}"
    version = dao.create_version(
        channel_name,
        package_name,
        package_format,
        "linux-64",
        "0.1",
        0,
        "",
        "",
        package_info,
        user.id,
    )

    yield version

    db.delete(version)
    db.delete(package)
    db.delete(channel)
    db.commit()


@pytest.fixture()
def other_user_without_profile(db):
    user = User(id=uuid.uuid4().bytes, username="other")
    db.add(user)
    return user


@pytest.fixture
def other_user(other_user_without_profile, db):
    profile = Profile(
        name="Other", avatar_url="http:///avatar", user=other_user_without_profile
    )
    db.add(profile)
    db.commit()
    yield other_user_without_profile


@pytest.fixture
def channel_role():
    return "owner"


@pytest.fixture
def public_channel(dao: Dao, user, channel_role):

    channel_name = "public-channel"

    channel_data = Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, channel_role)

    return channel
