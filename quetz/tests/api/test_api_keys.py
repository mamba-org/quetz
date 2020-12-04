import pytest

from quetz.db_models import ApiKey, ChannelMember, PackageMember


@pytest.fixture
def api_keys(other_user, user, db):

    keys = [
        ApiKey(key="key", description="key", user=user, owner=user),
        ApiKey(
            key="other_key", description="other_key", user=other_user, owner=other_user
        ),
        ApiKey(
            key="other_user_is_user",
            description="other_user_is_user",
            user=other_user,
            owner=user,
        ),
        ApiKey(
            key="user_is_user", description="user_is_user", user=user, owner=other_user
        ),
    ]

    for key in keys:
        db.add(key)

    db.commit()

    yield keys

    for key in keys:
        db.delete(key)
    db.commit()


@pytest.mark.parametrize(
    "user_role,target_key,expected_status",
    [
        ("owner", "other_key", 200),
        ("maintainer", "other_key", 200),
        ("member", "other_key", 403),
        (None, "other_key", 403),
        ("maintainer", "key", 200),
        ("member", "key", 200),
        (None, "key", 200),
        (None, "other_user_is_user", 200),
        (None, "user_is_user", 200),
    ],
)
def test_delete_api_key(auth_client, api_keys, db, target_key, expected_status):

    response = auth_client.delete(f"/api/api-keys/{target_key}")

    assert response.status_code == expected_status

    deleted_key = db.query(ApiKey).filter(ApiKey.key == target_key).one_or_none()

    if expected_status == 200:
        assert deleted_key.deleted
    else:
        assert not deleted_key.deleted


def test_delete_api_key_does_not_exist(auth_client):

    response = auth_client.delete("/api/api-keys/key")

    assert response.status_code == 404

    assert "does not exist" in response.json()["detail"]


def test_list_keys_with_channel_roles(
    auth_client, api_keys, db, user, other_user, private_channel
):

    channel_member = ChannelMember(
        channel=private_channel, user=user, role="maintainer"
    )
    db.add(channel_member)
    db.commit()

    response = auth_client.get("/api/api-keys")
    assert response.status_code == 200
    returned_keys = {key["description"]: key["roles"] for key in response.json()}
    assert len(returned_keys) == 2

    assert returned_keys["other_user_is_user"] == [
        {
            "channel": private_channel.name,
            "package": None,
            "role": "owner",
        }
    ]
    assert returned_keys["key"] == [
        {
            "channel": private_channel.name,
            "package": None,
            "role": "maintainer",
        }
    ]


def test_list_keys_with_package_roles(
    auth_client,
    api_keys,
    db,
    user,
    other_user,
    private_channel,
    private_package,
):

    package_member = PackageMember(
        channel=private_channel, package=private_package, user=user, role="maintainer"
    )
    db.add(package_member)
    db.commit()

    response = auth_client.get("/api/api-keys")
    assert response.status_code == 200
    returned_keys = {key["description"]: key["roles"] for key in response.json()}
    assert len(returned_keys) == 2

    assert returned_keys["other_user_is_user"] == [
        # package role
        {
            "channel": private_channel.name,
            "package": private_package.name,
            "role": "owner",
        },
        # channel role
        {
            "channel": private_channel.name,
            "package": None,
            "role": "owner",
        },
    ]
    assert returned_keys["key"] == [
        {
            "channel": private_channel.name,
            "package": private_package.name,
            "role": "maintainer",
        }
    ]


def test_list_keys_without_roles(auth_client, api_keys, db):
    pass


def test_unlist_delete_api_keys(auth_client, api_keys, db):

    response = auth_client.get("/api/api-keys")

    assert response.status_code == 200
    response_keys = response.json()
    assert len(response_keys) == len(api_keys)
    assert api_keys[0].description in [k["description"] for k in response.json()]

    api_keys[0].deleted = True
    db.commit()

    response = auth_client.list("/api/api-keys")
