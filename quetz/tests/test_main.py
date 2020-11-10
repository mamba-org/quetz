import datetime
import uuid
from unittest.mock import ANY

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
def package_version(db, user, channel_name, package_name):
    dao = Dao(db)
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
    profile = Profile(name="Other", avatar_url="http:///avatar", user=user)
    db.add(user)
    db.add(profile)
    db.commit()
    yield user


@pytest.fixture
def user_role():
    return None


@pytest.fixture
def user_with_role(user, user_role, db):
    # assign a role to the requester
    db_user = db.query(User).get(user.id)
    db_user.role = user_role
    db.commit()
    yield db_user


@pytest.fixture
def user_with_role_authenticated(user_with_role, client):

    session_user = user_with_role.username

    # log a user in
    response = client.get(f"/api/dummylogin/{session_user}")

    assert response.status_code == 200

    yield user_with_role


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
            "filename": "",
            "info": {},
            "uploader": {"name": "Bartosz", "avatar_url": "http:///avatar"},
            "time_created": ANY,
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


def test_validate_user_role_names(user, client, other_user, db):
    # test validation of role names

    response = client.put("/api/users/bartosz/role", json={"role": "UNDEFINED"})

    assert response.status_code == 422
    assert "member" in response.json()["detail"][0]["msg"]


@pytest.mark.parametrize(
    "target_user,user_role,target_user_role,expected_status",
    [
        ("other", None, "member", 403),
        ("other", "member", "member", 403),
        ("other", "member", "maintainer", 403),
        ("other", "member", "owner", 403),
        ("other", "maintainer", "member", 200),
        ("other", "maintainer", "maintainer", 403),
        ("other", "maintainer", "owner", 403),
        ("other", "owner", "member", 200),
        ("other", "owner", "maintainer", 200),
        ("other", "owner", "owner", 200),
        ("missing_user", "owner", "member", 404),
    ],
)
def test_set_user_role(
    user_with_role_authenticated,
    client,
    other_user,
    target_user,
    user_role,
    target_user_role,
    expected_status,
):

    # test changing role

    response = client.put(
        f"/api/users/{target_user}/role", json={"role": target_user_role}
    )
    assert response.status_code == expected_status

    # test if role assigned if previous request was successful
    if response.status_code == 200:

        get_response = client.get(f"/api/users/{target_user}/role")

        assert get_response.status_code == 200
        assert get_response.json()["role"] == target_user_role


@pytest.mark.parametrize(
    "target_user,user_role,expected_status",
    [
        ("other", None, 403),
        ("other", "member", 403),
        ("other", "maintainer", 200),
        ("other", "owner", 200),
        ("bartosz", None, 200),
        ("bartosz", "member", 200),
        ("bartosz", "maintainer", 200),
        ("bartosz", "owner", 200),
    ],
)
def test_get_user_role(
    user_with_role_authenticated, client, other_user, target_user, expected_status, db
):

    # test reading the role

    response = client.get(f"/api/users/{target_user}/role")
    assert response.status_code == expected_status

    expected_role = db.query(User).filter(User.username == target_user).first().role

    if response.status_code == 200:

        assert response.json()["role"] == expected_role


def test_get_set_user_role_without_login(user, client):
    # test permissions without logged-in user

    response = client.get("/api/users/bartosz/role")

    assert response.status_code == 401

    response = client.put("/api/users/bartosz/role", json={"role": "member"})

    assert response.status_code == 401


@pytest.mark.parametrize(
    "user_role,target_user,expected_status",
    [
        ("owner", "other", 200),
        ("maintainer", "other", 200),
        ("member", "other", 403),
        (None, "other", 403),
        ("owner", "bartosz", 200),
        ("maintainer", "bartosz", 200),
        ("member", "bartosz", 200),
        (None, "bartosz", 200),
    ],
)
def test_get_user_permissions(
    user_with_role_authenticated,
    other_user,
    target_user,
    client,
    expected_status,
):

    response = client.get(f"/api/users/{target_user}")

    assert response.status_code == expected_status

    if response.status_code == 200:
        assert response.json()["username"] == target_user


@pytest.mark.parametrize("paginated", [False, True])
@pytest.mark.parametrize(
    "user_role,query,expected_n_users",
    [
        ("owner", "", 2),
        ("maintainer", "", 2),
        ("member", "", 1),
        (None, "", 1),
        ("owner", "bar", 1),
        (None, "bar", 1),
        ("owner", "oth", 1),
        (None, "oth", 0),
    ],
)
def test_get_users_permissions(
    user_with_role_authenticated, other_user, client, expected_n_users, query, paginated
):

    if paginated:
        response = client.get(f"/api/paginated/users?q={query}")
        user_list = response.json()["result"]
    else:
        response = client.get(f"/api/users?q={query}")
        user_list = response.json()

    assert response.status_code == 200

    assert len(user_list) == expected_n_users


@pytest.mark.parametrize(
    "user_role,expected_status",
    [("owner", 201), ("maintainer", 201), ("member", 201), (None, 403)],
)
def test_create_normal_channel_permissions(
    client, user_with_role_authenticated, expected_status
):

    response = client.post(
        "/api/channels",
        json={
            "name": "test_create_channel",
            "private": False,
        },
    )
    assert response.status_code == expected_status
