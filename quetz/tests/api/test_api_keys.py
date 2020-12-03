import pytest

from quetz.db_models import ApiKey


@pytest.fixture
def api_keys(other_user, user, db):

    keys = [
        ApiKey(key='key', user=user, owner=user),
        ApiKey(key='other_key', user=other_user, owner=other_user),
        ApiKey(key='other_user_is_user', user=other_user, owner=user),
        ApiKey(key='user_is_user', user=user, owner=other_user),
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

    assert "does not exist" in response.json()['detail']
