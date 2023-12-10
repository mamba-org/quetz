import json
import os
import subprocess
import uuid

import pytest

import quetz
from quetz.db_models import Package, Profile, User
from quetz.rest_models import Channel
from quetz.tasks import indexing


@pytest.fixture
def user(db):
    user = User(id=uuid.uuid4().bytes, username="bartosz")
    profile = Profile(name="Bartosz", avatar_url="http:///avatar", user=user)
    db.add(user)
    db.add(profile)
    db.commit()
    yield user


@pytest.fixture
def channel_name():
    return "my-channel"


@pytest.fixture
def package_name():
    return "mytestpackage"


@pytest.fixture
def package_format():
    return "tarbz2"


@pytest.fixture
def package_file_name(package_name, package_format):
    if package_format == "tarbz2":
        return f"{package_name}-0.1-0.tar.bz2"
    elif package_format == "conda":
        return f"{package_name}-0.1-0.conda"


@pytest.fixture
def channel(dao: "quetz.dao.Dao", channel_name, user):
    channel_data = Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, "owner")
    return channel


@pytest.fixture
def package_subdir():
    return "noarch"


@pytest.fixture
def package_version(
    dao: "quetz.dao.Dao",
    user,
    channel,
    package_name,
    db,
    package_file_name,
    package_format,
    package_subdir,
):
    channel_data = json.dumps({"subdirs": [package_subdir]})
    package_data = Package(name=package_name)

    package = dao.create_package(channel.name, package_data, user.id, "owner")
    package.channeldata = channel_data
    db.commit()

    package_info = (
        '{"run_exports": {"weak": ["otherpackage > 0.1"]}, "size": 100, "depends": []}'
    )
    version = dao.create_version(
        channel.name,
        package_name,
        package_format,
        package_subdir,
        "0.1",
        "0",
        "0",
        package_file_name,
        package_info,
        user.id,
        size=0,
    )

    yield version


@pytest.fixture
def archive_format():
    return "tarbz2"


@pytest.fixture
def pkgstore(config):
    pkgstore = config.get_package_store()
    return pkgstore


def test_repodata_zchunk(
    pkgstore,
    package_version,
    channel_name,
    package_file_name,
    dao,
    db,
    config,
):
    indexing.update_indexes(
        dao, pkgstore, channel_name, compression=config.get_compression_config()
    )

    index_path = os.path.join(
        pkgstore.channels_dir,
        channel_name,
        "noarch",
        "index.html",
    )

    assert os.path.isfile(index_path)
    with open(index_path, "r") as fid:
        content = fid.read()

    assert "repodata.json" in content
    assert "repodata.json.bz2" in content
    assert "repodata.json.zck" in content

    for fname in ("repodata.json", "repodata.json.zck"):
        repodata_path = os.path.join(
            pkgstore.channels_dir, channel_name, "noarch", fname
        )

        assert os.path.isfile(repodata_path)

        if fname.endswith(".zck"):
            subprocess.check_call(["unzck", repodata_path])
            with open("repodata.json") as f:
                repodata_unzck = f.read()

            assert repodata == repodata_unzck  # NOQA # type: ignore
        else:
            with open(repodata_path) as f:
                repodata = f.read()  # NOQA
