import datetime
from unittest.mock import ANY

import pytest

from quetz.metrics.db_models import PackageVersionMetric


def test_get_package_list(package_version, package_name, channel_name, client):

    response = client.get("/api/dummylogin/bartosz")
    response = client.get(
        f"/api/channels/{channel_name}/packages/{package_name}/versions"
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": ANY,
            "channel_name": "my-channel",
            "package_name": "my-package",
            "platform": "linux-64",
            "version": "0.1",
            "build_string": "",
            "build_number": 0,
            "filename": "test-package-0.1-0.tar.bz2",
            "info": {},
            "uploader": {"name": "Bartosz", "avatar_url": "http:///avatar"},
            "time_created": ANY,
            "download_count": 0,
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


@pytest.mark.parametrize(
    "channel_role,expected_code",
    [("owner", 201), ("maintainer", 201), ("member", 403), (None, 403)],
)
def test_add_package_permissions(auth_client, public_channel, expected_code):

    response = auth_client.post(
        f"/api/channels/{public_channel.name}/packages",
        json={"name": "test-package", "summary": "none", "description": "none"},
    )

    assert response.status_code == expected_code


@pytest.mark.parametrize(
    "channel_role,expected_code",
    [("owner", 200), ("maintainer", 200), ("member", 403), (None, 403)],
)
def test_get_channel_members(auth_client, public_channel, expected_code):

    response = auth_client.get(f"/api/channels/{public_channel.name}/members")

    assert response.status_code == expected_code


@pytest.mark.parametrize(
    "role,expected_code",
    [
        ("owner", 201),
        ("maintainer", 201),
        ("member", 201),
        ("invalid", 422),
    ],
)
def test_post_channel_member(
    auth_client, public_channel, other_user, role, expected_code
):

    response = auth_client.post(
        f"/api/channels/{public_channel.name}/members",
        json={"username": other_user.username, "role": role},
    )

    assert response.status_code == expected_code

    if expected_code == 201:
        response = auth_client.get(f"/api/channels/{public_channel.name}/members")
        response.raise_for_status()
        for element in response.json():
            if element["user"]["username"] == other_user.username:
                assert element["role"] == role
                break
        else:
            raise RuntimeError(f"User '{other_user.username}' not found.")


def test_post_channel_member_unknown_user(auth_client, public_channel):

    response = auth_client.post(
        f"/api/channels/{public_channel.name}/members",
        json={"username": "unknown-user", "role": "member"},
    )

    assert response.status_code == 404


def test_delete_channel_member(auth_client, public_channel, other_user):

    auth_client.post(
        f"/api/channels/{public_channel.name}/members",
        json={"username": other_user.username, "role": "member"},
    )

    response = auth_client.delete(
        f"/api/channels/{public_channel.name}/members",
        params={"username": other_user.username},
    )

    assert response.status_code == 200


def test_delete_channel_member_no_member(auth_client, public_channel, other_user):

    response = auth_client.delete(
        f"/api/channels/{public_channel.name}/members",
        params={"username": other_user.username},
    )

    assert response.status_code == 404


def test_upload_wrong_file_type(auth_client, public_channel):
    files = {"files": ("my_package-0.1-0.tar.bz", "dfdf")}
    response = auth_client.post(
        f"/api/channels/{public_channel.name}/files/", files=files
    )
    assert response.status_code == 400
    assert "not a bzip2 file" in response.json()['detail']


def test_increment_download_count(
    auth_client, public_channel, package_version, db, mocker
):
    def get_db(config):
        yield db

    mocker.patch("quetz.main.get_db", get_db)

    assert not db.query(PackageVersionMetric).one_or_none()

    with auth_client:
        response = auth_client.get(
            f"/get/{public_channel.name}/linux-64/test-package-0.1-0.tar.bz2"
        )
        assert response.status_code == 200

    metrics = (
        db.query(PackageVersionMetric)
        .filter(PackageVersionMetric.channel_name == public_channel.name)
        .filter(PackageVersionMetric.platform == package_version.platform)
        .filter(PackageVersionMetric.filename == package_version.filename)
        .all()
    )

    assert len(metrics) > 1
    assert metrics[0].count == 1
    db.refresh(package_version)
    assert package_version.download_count == 1

    with auth_client:
        response = auth_client.get(
            f"/get/{public_channel.name}/linux-64/test-package-0.1-0.tar.bz2"
        )

    assert response.status_code == 200

    db.refresh(metrics[0])
    assert metrics[0].count == 2
    db.refresh(package_version)
    assert package_version.download_count == 2
