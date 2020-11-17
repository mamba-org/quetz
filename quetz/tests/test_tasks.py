from unittest import mock

import pytest

from quetz.db_models import Channel
from quetz.pkgstores import PackageStore
from quetz.tasks import reindex_packages_from_store


@pytest.fixture
def channel_name():
    return "my-channel"


@pytest.fixture
def pkgstore(config):
    pkgstore = config.get_package_store()
    return pkgstore


@pytest.fixture
def package_files(pkgstore: PackageStore, channel_name):
    pkgstore.create_channel(channel_name)
    filename = "test-package-0.1-0.tar.bz2"
    with open(filename, 'rb') as fid:
        content = fid.read()
    pkgstore.add_file(content, channel_name, f"linux-64/{filename}")


@pytest.fixture
def channel(dao, user, channel_name):

    channel_data = Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, "owner")

    return channel


def test_reindex_package_files(config, user, package_files, channel, db):
    user_id = user.id
    with mock.patch("quetz.tasks.get_session", lambda _: db):
        reindex_packages_from_store(config, channel.name, user_id)
    db.refresh(channel)

    assert channel.packages
    assert channel.packages[0].name == "test-package"
    assert channel.packages[0].members[0].user.username == user.username
    assert channel.packages[0].package_versions[0].version == '0.1'
