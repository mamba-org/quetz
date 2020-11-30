import datetime
import uuid
from unittest.mock import ANY

import pytest

from quetz import db_models
from quetz.config import Config
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
    auth_client,
    other_user,
    target_user,
    user_role,
    target_user_role,
    expected_status,
):

    # test changing role

    response = auth_client.put(
        f"/api/users/{target_user}/role", json={"role": target_user_role}
    )
    assert response.status_code == expected_status

    # test if role assigned if previous request was successful
    if response.status_code == 200:

        get_response = auth_client.get(f"/api/users/{target_user}/role")

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
def test_get_user_role(auth_client, other_user, target_user, expected_status, db):

    # test reading the role

    response = auth_client.get(f"/api/users/{target_user}/role")
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
    other_user,
    target_user,
    auth_client,
    expected_status,
):

    response = auth_client.get(f"/api/users/{target_user}")

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
    other_user, auth_client, expected_n_users, query, paginated
):

    if paginated:
        response = auth_client.get(f"/api/paginated/users?q={query}")
        user_list = response.json()["result"]
    else:
        response = auth_client.get(f"/api/users?q={query}")
        user_list = response.json()

    assert response.status_code == 200

    assert len(user_list) == expected_n_users


@pytest.mark.parametrize(
    "user_role,expected_status",
    [("owner", 201), ("maintainer", 201), ("member", 201), (None, 403)],
)
def test_create_normal_channel_permissions(auth_client, expected_status):

    response = auth_client.post(
        "/api/channels",
        json={
            "name": "test_create_channel",
            "private": False,
        },
    )
    assert response.status_code == expected_status


@pytest.mark.parametrize("channel_role", ["owner", "maintainer", "member"])
@pytest.mark.parametrize("user_role", ["owner", "maintainer", "member", None])
def test_delete_channel_permissions(
    db, auth_client, public_channel, user_role, channel_role
):

    response = auth_client.delete("/api/channels/public-channel")

    channel = (
        db.query(db_models.Channel)
        .filter(db_models.Channel.name == "public-channel")
        .one_or_none()
    )

    if user_role in ["owner", "maintainer"] or channel_role in ["owner", "maintainer"]:
        assert response.status_code == 200
        assert channel is None
    else:
        assert response.status_code == 403
        assert channel is not None


@pytest.mark.parametrize("user_role", ["owner"])
def test_delete_channel_with_packages(
    db, auth_client, private_channel, private_package_version, config: Config
):

    pkg_store = config.get_package_store()
    pkg_store.add_file("test-file", private_channel.name, "test_file.txt")
    pkg_store.add_file("second", private_channel.name, "subdir/second_file.txt")

    response = auth_client.delete(f"/api/channels/{private_channel.name}")

    channel = (
        db.query(db_models.Channel)
        .filter(db_models.Channel.name == private_channel.name)
        .one_or_none()
    )

    version = (
        db.query(db_models.PackageVersion)
        .filter_by(package_name=private_package_version.package_name)
        .one_or_none()
    )
    package = (
        db.query(db_models.Package)
        .filter_by(name=private_package_version.package_name)
        .one_or_none()
    )

    files = pkg_store.list_files(private_channel.name)

    assert response.status_code == 200
    assert channel is None
    assert version is None
    assert package is None
    assert not files


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/channels/{channel_name}",
        "/api/channels/{channel_name}/packages",
        "/api/channels/{channel_name}/packages/{package_name}",
        "/api/channels/{channel_name}/packages/{package_name}/versions",
    ],
)
@pytest.mark.parametrize(
    "user_role,expected_status",
    [("owner", 200), ("maintainer", 200), ("member", 403), (None, 403)],
)
def test_permissions_channel_endpoints(
    auth_client,
    private_channel,
    expected_status,
    endpoint,
    private_package,
    private_package_version,
):

    response = auth_client.get(
        endpoint.format(
            channel_name=private_channel.name, package_name=private_package.name
        )
    )
    assert response.status_code == expected_status


@pytest.fixture
def channel_role():
    return "owner"


@pytest.fixture
def public_channel(dao: Dao, user, channel_role):

    channel_name = "public-channel"

    channel_data = Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, channel_role)

    return channel


@pytest.mark.parametrize("user_role", ["owner"])
def test_get_users_without_profile(auth_client, other_user_without_profile, user):

    response = auth_client.get("/api/users")

    assert response.status_code == 200
    users = response.json()
    assert len(users) == 1
    assert users[0]["username"] == user.username

    response = auth_client.get(f"/api/users/{other_user_without_profile.username}")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "channel_role,expected_code",
    [("owner", 200), ("maintainer", 200), ("member", 403), (None, 403)],
)
def test_channel_action_reindex(auth_client, public_channel, expected_code):

    response = auth_client.put(
        f"/api/channels/{public_channel.name}/actions", json={"action": "reindex"}
    )

    assert response.status_code == expected_code


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


def test_upload_wrong_file_type(auth_client, public_channel):
    files = {"files": ("my_package-0.1.tar.bz", "dfdf")}
    response = auth_client.post(
        f"/api/channels/{public_channel.name}/files/", files=files
    )
    assert response.status_code == 400
    assert "not a bzip2 file" in response.json()['detail']
