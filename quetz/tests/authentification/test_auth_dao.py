from quetz.authentication import auth_dao


def test_get_user_by_identity_new_user(dao, config):

    profile = {
        "id": 4567,
        "login": "bartosz",
        "name": "bartosz",
        "avatar_url": "url",
    }
    provider = "github"

    user = auth_dao.get_user_by_identity(dao, provider, profile, config)

    assert user.username == 'bartosz'
    assert user.identities[0].provider == 'github'
    assert user.identities[0].identity_id == '4567'
