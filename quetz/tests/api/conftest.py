import uuid
from pathlib import Path

import pytest

from quetz.config import Config
from quetz.dao import Dao
from quetz.db_models import Identity, PackageVersion, Profile, User
from quetz.rest_models import Channel, Package


@pytest.fixture
def package_name():
    return "my-package"


@pytest.fixture
def channel_name():
    return "my-channel"


@pytest.fixture
def private_channel(dao, other_user):

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
def private_package_version(dao, private_channel, private_package, other_user, config):
    package_format = "tarbz2"
    package_info = "{}"
    channel_name = private_channel.name
    filename = Path("test-package-0.1-0.tar.bz2")

    pkgstore = config.get_package_store()
    with open(filename, "rb") as fid:
        pkgstore.add_file(fid.read(), channel_name, "linux-64" / filename)

    platform = "linux-64"
    version = dao.create_version(
        private_channel.name,
        private_package.name,
        package_format,
        platform,
        "0.1",
        "0",
        "",
        str(filename),
        package_info,
        other_user.id,
        size=0,
    )

    dao.update_package_channeldata(
        private_channel.name,
        private_package.name,
        {'name': package_name, 'subdirs': [platform]},
    )

    return version


@pytest.fixture
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


@pytest.fixture
def package_version(db, make_package_version):
    version = make_package_version("test-package-0.1-0.tar.bz2", "0.1")

    return version


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
    identity = Identity(
        provider="github",
        identity_id="github",
        username="btel",
        user=other_user_without_profile,
    )
    db.add(profile)
    db.add(identity)
    db.commit()
    yield other_user_without_profile


@pytest.fixture
def channel_role():
    return "owner"


@pytest.fixture
def package_role():
    return "owner"


@pytest.fixture
def public_channel(dao: Dao, user, channel_role, channel_name):

    channel_data = Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, channel_role)

    return channel


@pytest.fixture
def public_package(db, user, public_channel, dao, package_role, package_name):

    package_data = Package(name=package_name)

    package = dao.create_package(
        public_channel.name, package_data, user.id, package_role
    )

    return package


@pytest.fixture
def pkgstore(config):
    return config.get_package_store()
