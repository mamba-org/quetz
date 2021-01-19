from quetz import dao_github


def test_get_user_by_github_identity_new_user(dao, config):

    profile = {
        "id": 4567,
        "login": "bartosz",
        "name": "bartosz",
        "avatar_url": "url",
        "provider": "github",
    }

    user = dao_github.get_user_by_github_identity(dao, profile, config)

    assert user.username == 'bartosz'
    assert user.identities[0].provider == 'github'
    assert user.identities[0].identity_id == '4567'
