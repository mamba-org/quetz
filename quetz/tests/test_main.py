import datetime
from unittest.mock import ANY

import pytest

from quetz.dao import Dao
from quetz.rest_models import Channel, Package


@pytest.fixture
def package_name():
    return "my-package"


@pytest.fixture
def channel_name():
    return "my-channel"


@pytest.fixture
def package_version(db, user, channel_name, package_name):
    dao = Dao(db)
    channel_data = Channel(name=channel_name, private=False)
    package_data = Package(name=package_name)

    channel, channel_member = dao.create_channel(channel_data, user.id, "owner")
    package, package_member = dao.create_package(
        channel_name, package_data, user.id, "owner"
    )
    package_format = 'tarbz2'
    package_info = "{}"
    version = dao.create_version(
        channel_name,
        package_name,
        package_format,
        "linux-64",
        "0.1",
        "0",
        "",
        "",
        package_info,
        user.id,
    )

    yield version

    db.delete(version)
    db.delete(package_member)
    db.delete(package)
    db.delete(channel_member)
    db.delete(channel)
    db.commit()


def test_get_package_list(package_version, package_name, channel_name, client):

    response = client.get("/api/dummylogin/bartosz")
    response = client.get(
        f"/api/channels/{channel_name}/packages/{package_name}/versions"
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            'id': ANY,
            'channel_name': 'my-channel',
            'package_name': 'my-package',
            'platform': 'linux-64',
            'version': '0.1',
            'build_string': '',
            'build_number': 0,
            'filename': '',
            'info': {},
            'uploader': {'name': 'Bartosz', 'avatar_url': 'http:///avatar'},
            'time_created': ANY,
        }
    ]


def test_package_version_list_by_date(
    package_version, package_name, channel_name, client
):

    now = datetime.datetime.utcnow()
    later = now + datetime.timedelta(minutes=1)
    earlier = now - datetime.timedelta(minutes=1)

    response = client.get("/api/dummylogin/bartosz")
    response = client.get(
        f"/api/channels/{channel_name}/packages/{package_name}/versions"
        "?time_created__ge=" + later.isoformat()
    )

    assert response.status_code == 200
    assert response.json() == []

    response = client.get(
        f"/api/channels/{channel_name}/packages/{package_name}/versions"
        "?time_created__ge=" + earlier.isoformat()
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
