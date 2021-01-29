import pytest

from quetz.dao import Dao
from quetz.db_models import ApiKey, ChannelMember, PackageMember
from quetz.rest_models import BaseApiKey
from quetz.utils import generate_random_key


@pytest.fixture
def api_keys(other_user, user, db, dao: Dao):
    def key_factory(key_user, descr, expire_at, roles):
        return dao.create_api_key(
            key_user.id,
            BaseApiKey.parse_obj(
                dict(description=descr, expire_at=expire_at, roles=roles)
            ),
            descr,
        )

    keys = [
        key_factory(user, "key", '2030-01-01', []),
        key_factory(other_user, "other_key", '2030-01-01', []),
        key_factory(other_user, "other_user_is_user", '2030-01-01', []),
        key_factory(user, "user_is_user", '2030-01-01', []),
    ]

    yield {k.description: k for k in keys}

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
        (None, "other_user_is_user", 403),
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

    assert returned_keys["user_is_user"] is None
    assert returned_keys["key"] is None


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

    assert returned_keys["user_is_user"] is None
    assert returned_keys["key"] is None


def test_list_keys_subrole(auth_client, dao, user, private_channel):

    dao.create_api_key(
        user.id,
        BaseApiKey.parse_obj(
            dict(
                description="user-key",
                roles=[
                    {"channel": private_channel.name, 'package': None, "role": "owner"}
                ],
            )
        ),
        "user-key",
    )

    response = auth_client.get("/api/api-keys")
    returned_keys = {key["description"]: key["roles"] for key in response.json()}
    assert len(returned_keys) == 1
    assert "user-key" in returned_keys
    assert returned_keys['user-key'] == [
        {"channel": private_channel.name, "package": None, "role": "owner"}
    ]


def test_list_keys_without_roles(auth_client, dao, user):

    dao.create_api_key(
        user.id,
        BaseApiKey.parse_obj(dict(description="user-key", roles=[])),
        "user-key",
    )

    response = auth_client.get("/api/api-keys")
    assert response.status_code == 200
    returned_keys = {key["description"]: key["roles"] for key in response.json()}
    assert len(returned_keys) == 1
    assert "user-key" in returned_keys
    assert returned_keys['user-key'] is None


def test_unlist_delete_api_keys(auth_client, api_keys, db, private_channel, user):

    channel_member = ChannelMember(
        channel=private_channel, user=user, role="maintainer"
    )
    db.add(channel_member)
    db.commit()

    response = auth_client.get("/api/api-keys")

    assert response.status_code == 200
    returned_keys = {key["description"]: key["roles"] for key in response.json()}
    assert "key" in returned_keys

    api_keys["key"].deleted = True
    db.commit()

    response = auth_client.get("/api/api-keys")
    assert response.status_code == 200

    returned_keys = {key["description"]: key["roles"] for key in response.json()}
    assert "key" not in returned_keys


@pytest.mark.parametrize("loop", [i + 1 for i in range(100)])
def test_generate_random_key(loop):
    key = generate_random_key()
    assert len(key) == 32
    assert key.isalnum()


@pytest.mark.parametrize("length", [i + 1 for i in range(100)])
def test_generate_random_key_variable_length(length):
    key = generate_random_key(length)
    assert len(key) == length
    assert key.isalnum()
