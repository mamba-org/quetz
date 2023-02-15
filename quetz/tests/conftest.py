"""py.test fixtures

Fixtures for Quetz components
-----------------------------
- `db`

"""
# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.


import uuid
from pathlib import Path

from pytest import fixture

from quetz.config import Config
from quetz.dao import Dao
from quetz.db_models import PackageVersion, Profile, User
from quetz.rest_models import Channel, Package

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


@fixture
def make_package_version(
    db,
    user,
    public_channel,
    channel_name,
    package_name,
    public_package,
    dao: Dao,
    config: Config,
):
    pkgstore = config.get_package_store()

    versions = []

    def _make_package_version(filename, version_number, platform="linux-64"):
        filename = Path(filename)
        with open(filename, "rb") as fid:
            pkgstore.add_file(fid.read(), channel_name, platform / filename)
        package_format = "tarbz2"
        package_info = "{}"
        version = dao.create_version(
            channel_name,
            package_name,
            package_format,
            platform,
            version_number,
            0,
            "",
            str(filename),
            package_info,
            user.id,
            size=11,
        )

        dao.update_package_channeldata(
            channel_name,
            package_name,
            {'name': package_name, 'subdirs': [platform]},
        )

        dao.update_channel_size(channel_name)

        versions.append(version)

        return version

    yield _make_package_version

    for version in versions:
        db.query(PackageVersion).filter(PackageVersion.id == version.id).delete()
    db.commit()


@fixture
def package_version(db, make_package_version):
    version = make_package_version("test-package-0.1-0.tar.bz2", "0.1")

    return version


@fixture
def public_channel(dao: Dao, user, channel_role, channel_name):
    channel_data = Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, channel_role)

    return channel


@fixture
def public_package(db, user, public_channel, dao, package_role, package_name):
    package_data = Package(name=package_name)

    package = dao.create_package(
        public_channel.name, package_data, user.id, package_role
    )

    return package


@fixture
def channel_name():
    return "my-channel"


@fixture
def package_name():
    return "my-package"


@fixture
def channel_role():
    return "owner"


@fixture
def package_role():
    return "owner"
