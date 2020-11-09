import datetime
import uuid
from unittest.mock import ANY

import pytest

from quetz.dao import Dao
from quetz.db_models import User
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

    channel = dao.create_channel(channel_data, user.id, "owner")
    package = dao.create_package(channel_name, package_data, user.id, "owner")
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
    db.delete(package)
    db.delete(channel)
    db.commit()


@pytest.fixture
def other_user(db):
    user = User(id=uuid.uuid4().bytes, username="other")
    db.add(user)
    db.commit()
    yield user


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


def test_get_set_user_role(user, client, other_user, db):

    # test permissions without logged-in user

    response = client.get("/api/users/bartosz/role")

    assert response.status_code == 403

    response = client.put("/api/users/bartosz/role", json={"role": "member"})

    assert response.status_code == 403

    # log a user in
    response = client.get("/api/dummylogin/bartosz")

    assert response.status_code == 200

    # no permission for a different user

    response = client.get(f"/api/users/{other_user.username}/role")
    assert response.status_code == 403

    response = client.put(
        f"/api/users/{other_user.username}/role", json={"role": "member"}
    )
    assert response.status_code == 403

    # ok to check role for oneself

    response = client.get(f"/api/users/{user.username}/role")
    assert response.status_code == 200
    assert response.json() == {"role": None}

    # no permission to change own role for non-maintainers/owners

    response = client.put(f"/api/users/{user.username}/role", json={"role": "member"})
    assert response.status_code == 403

    # maintainer/owner can read roles for other users

    user.role = "maintainer"
    db.commit()

    response = client.get(f"/api/users/{user.username}/role")
    assert response.status_code == 200
    assert response.json() == {"role": "maintainer"}

    response = client.get(f"/api/users/{other_user.username}/role")
    assert response.status_code == 200
    assert response.json() == {"role": None}

    # maintainer can only elevate role to member

    response = client.put(
        f"/api/users/{other_user.username}/role", json={"role": "member"}
    )

    assert response.status_code == 200

    response = client.get(f"/api/users/{other_user.username}/role")

    assert response.status_code == 200
    assert response.json() == {"role": "member"}

    # only owner can elevate the role to maintainer or owner

    user.role = "owner"
    db.commit()

    for role_name in ["member", "maintainer", "owner"]:
        response = client.put(
            f"/api/users/{other_user.username}/role", json={"role": role_name}
        )

        assert response.status_code == 200

        response = client.get(f"/api/users/{other_user.username}/role")

        assert response.status_code == 200
        assert response.json() == {"role": role_name}

    # test validation of role names

    response = client.put("/api/users/bartosz/role", json={"role": "UNDEFINED"})

    assert response.status_code == 422
    assert "member" in response.json()["detail"][0]["msg"]
