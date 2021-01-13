import uuid

import pytest

from quetz.db_models import ApiKey, ChannelMember, PackageMember, User


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


@pytest.fixture
def api_keys(user, other_user, db):

    users = [user, other_user]

    for key_user in users:
        for key_owner in users:
            key = ApiKey(key=str(uuid.uuid4()), user=key_user, owner=key_owner)
            db.add(key)

    db.commit()


@pytest.mark.parametrize(
    "user_role,target_user,expected_status",
    [
        ("owner", "other", 200),
        ("maintainer", "other", 200),
        ("member", "other", 403),
        (None, "other", 403),
        # user can always remove oneself
        ("maintainer", "bartosz", 200),
        ("member", "bartosz", 200),
        (None, "bartosz", 200),
    ],
)
def test_delete_user_permission(
    other_user, auth_client, db, user_role, target_user, expected_status, user, api_keys
):

    response = auth_client.delete(f"/api/users/{target_user}")

    deleted_user = db.query(User).filter(User.username == target_user).one_or_none()

    if expected_status == 200:
        assert response.status_code == 200
        assert deleted_user
        assert not deleted_user.profile
        assert not deleted_user.identities
        assert not deleted_user.api_keys_owner
        assert not deleted_user.api_keys_user

    else:
        assert response.status_code == expected_status
        assert deleted_user
        assert deleted_user.profile
        assert deleted_user.identities
        assert deleted_user.api_keys_owner
        assert deleted_user.api_keys_user

    # check if other users were not accidently removed
    existing_user = db.query(User).filter(User.username != target_user).one_or_none()
    assert existing_user
    assert existing_user.profile
    assert existing_user.api_keys_owner
    assert existing_user.api_keys_user


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
    "http_user,expected_role", [("bartosz", "member"), ("other", "owner")]
)
def test_list_user_channels(
    user, client, other_user, db, private_channel, http_user, expected_role
):

    member = ChannelMember(
        channel_name=private_channel.name, user_id=user.id, role="member"
    )
    db.add(member)
    db.commit()

    response = client.get(f"/api/dummylogin/{http_user}")
    assert response.status_code == 200

    response = client.get(f"/api/users/{http_user}/channels")
    assert response.status_code == 200

    assert response.json() == [{"name": private_channel.name, "role": expected_role}]

    response = client.get(f"/api/paginated/users/{http_user}/channels")
    assert response.status_code == 200

    assert response.json()["result"] == [
        {"name": private_channel.name, "role": expected_role}
    ]


@pytest.mark.parametrize(
    "http_user,expected_role", [("bartosz", "member"), ("other", "owner")]
)
@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/users/{http_user}/packages",
        "/api/paginated/users/{http_user}/packages",
    ],
)
def test_list_user_packages(
    user,
    client,
    other_user,
    db,
    private_channel,
    private_package,
    http_user,
    expected_role,
    endpoint,
):
    member = PackageMember(
        channel=private_channel, package=private_package, user=user, role="member"
    )
    db.add(member)
    db.commit()

    response = client.get(f"/api/dummylogin/{http_user}")
    assert response.status_code == 200

    response = client.get(endpoint.format(http_user=http_user))
    assert response.status_code == 200

    data = response.json()

    if "result" in data:
        data = data["result"]

    assert data == [
        {
            "name": private_package.name,
            "channel_name": private_channel.name,
            "role": expected_role,
        }
    ]
