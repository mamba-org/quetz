import json

import pytest

from quetz.db_models import Channel
from quetz.pkgstores import PackageStore
from quetz.tasks.reindexing import reindex_packages_from_store


@pytest.fixture
def channel_name():
    return "my-channel"


@pytest.fixture
def pkgstore(config):
    pkgstore = config.get_package_store()
    return pkgstore


@pytest.fixture
def package_filenames():
    return ["test-package-0.1-0.tar.bz2", "test-package-0.2-0.tar.bz2"]


@pytest.fixture
def package_files(pkgstore: PackageStore, channel_name, package_filenames):
    pkgstore.create_channel(channel_name)
    for filename in package_filenames:
        with open(filename, 'rb') as fid:
            content = fid.read()
        pkgstore.add_file(content, channel_name, f"linux-64/{filename}")


@pytest.fixture
def channel(dao, user, channel_name):

    channel_data = Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, "owner")

    return channel


def test_reindex_package_files(
    config,
    user,
    package_files,
    channel,
    db,
    dao,
    pkgstore: PackageStore,
    package_filenames,
):
    user_id = user.id
    reindex_packages_from_store(dao, config, channel.name, user_id)
    db.refresh(channel)

    assert channel.packages
    assert channel.packages[0].name == "test-package"
    assert channel.packages[0].members[0].user.username == user.username
    assert channel.packages[0].package_versions[0].version == '0.1'
    assert channel.packages[0].package_versions[1].version == '0.2'

    repodata = pkgstore.serve_path(channel.name, "linux-64/repodata.json")
    repodata = json.load(repodata)
    assert repodata
    assert len(repodata['packages']) == 2
    assert set(repodata["packages"].keys()) == set(package_filenames)
