import time

import pytest
from authlib.jose import JsonWebKey, jwt
from authlib.oidc.core.util import create_half_hash
from fastapi.testclient import TestClient

from quetz.authentication import github as auth_github
from quetz.authentication import google as auth_google
from quetz.authentication.jupyterhub import JupyterhubAuthenticator
from quetz.authorization import SERVER_OWNER
from quetz.dao import Dao
from quetz.db_models import Channel, ChannelMember, Identity, Profile, User
from quetz.testing.utils import AsyncPathMapDispatch


@pytest.fixture
def default_role():
    return "member"


@pytest.fixture
def user_roles():
    return {"admins": [], "members": [], "maintainers": []}


@pytest.fixture
def config_extra(default_role, user_roles):
    config_values = ["[users]"]
    if default_role:
        config_values.append(f'default_role = "{default_role}"')
    for group in ['admins', 'members', 'maintainers']:
        group_users = user_roles.get(group, [])
        config_values.append(f'{group} = {group_users}')
    return "\n".join(config_values)


@pytest.fixture
def login():
    return "user-with-role"


@pytest.fixture
def github_response(config, login):

    response = {
        '/login/oauth/access_token': {'body': {'access_token': 'b'}},
        '/user': {
            "body": {
                "login": login,
                "avatar_url": "",
                "id": login + "_id",
                "name": "monalisa",
            }
        },
    }

    return "test_github", response


@pytest.fixture
def jupyter_response(config, login):

    response = {
        '/hub/api/oauth2/token': {
            'body': {'access_token': 'b', 'token_type': 'Bearer'}
        },
        '/hub/api/authorizations/token/b': {
            "body": {
                "name": login,
            }
        },
    }

    return "test_jupyter", response


@pytest.fixture
def google_response(config, login):

    user_claims = {
        "picture": "http://avatar",
        "name": "monalisa",
    }
    access_token = "b"
    payload = {
        "iss": "https://accounts.google.com",
        "azp": config.google_client_id,
        "aud": "1234987819200.apps.googleusercontent.com",
        "sub": login + "_id",
        "at_hash": create_half_hash(access_token, "RS256").decode("ascii"),
        "hd": "example.com",
        "email": login,
        "email_verified": "true",
        "iat": int(time.time()),
        "exp": int(time.time()) + 100,
        "nonce": "0394852-3190485-2490358",
        **user_claims,
    }

    header = {"alg": "RS256", "kid": "1"}
    with open("private.pem") as fid:
        key = fid.read()
    with open("cert.pem") as fid:
        cert = fid.read()
    id_token = jwt.encode(header, payload, key).decode('ascii')
    response = {
        '/token': {'body': {'access_token': access_token, "id_token": id_token}},
        '/oauth2/v3/certs': {
            "body": {
                "keys": [
                    {
                        "kid": "1",
                        **JsonWebKey.import_key(cert, {"kty": "RSA"}).as_dict(),
                    }
                ]
            }
        },
        '/.well-known/openid-configuration': {
            "body": {
                "issuer": "https://accounts.google.com",
                "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",  # noqa
                "device_authorization_endpoint": "https://oauth2.googleapis.com/device/code",  # noqa
                "token_endpoint": "https://oauth2.googleapis.com/token",
                "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
                "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
            }
        },
    }

    return "test_google", response


@pytest.fixture
def config_auth():
    return """
[github]
client_id = "aaa"
client_secret = "bbb"

[google]
client_id = "aaa"
client_secret = "bbb"

[jupyterhubauthenticator]
client_id = "test_client"
client_secret = "test_secret"
access_token_url = "http://jupyterhub/hub/api/oauth2/token"
authorize_url = "http://jupyterhub/hub/api/oauth2/authorize"
api_base_url = "http://jupyterhub/hub/api/"
"""


@pytest.fixture(
    params=[
        "github_response",
        "google_response",
        "jupyter_response",
    ]
)
def oauth_server(request, config, app):
    provider, response = request.getfixturevalue(request.param)

    server_app = AsyncPathMapDispatch(response)

    # we need to remove the client, because it might have been already
    # registered in quetz.main

    if provider == 'test_github':
        auth_module = auth_github.GithubAuthenticator
    elif provider == "test_google":
        auth_module = auth_google.GoogleAuthenticator
    elif provider == 'test_jupyter':
        auth_module = JupyterhubAuthenticator
    else:
        raise Exception(f"not recognised provider {provider}")

    module = auth_module(
        config,
        client_kwargs={'app': server_app},
        provider=provider,
        app=app,
    )

    yield module

    module.oauth._registry.pop(provider)
    module.oauth._clients.pop(provider)


@pytest.fixture
def routed_client(app, oauth_server):

    # need to prepend the routes so that frontend routes do not
    # take priority
    for route in oauth_server.router.routes:
        app.router.routes.insert(0, route)

    yield TestClient(app)

    for route in oauth_server.router.routes:
        app.router.routes.remove(route)


@pytest.mark.parametrize("config_extra", ["[users]\ncreate_default_channel = true"])
def test_config_create_default_channel(routed_client, db, oauth_server, config):

    response = routed_client.get(f'/auth/{oauth_server.provider}/authorize')

    assert response.status_code == 200

    user = db.query(User).filter(User.username == "user-with-role").one_or_none()
    assert user

    channel = db.query(Channel).filter(Channel.name == "user-with-role").one_or_none()

    assert channel
    assert user == channel.members[0].user


@pytest.mark.parametrize("default_role", [None, 'member'])
@pytest.mark.parametrize(
    "user_roles,expected_role",
    [
        ({"admins": ["test_github:user-with-role"]}, "owner"),
        ({"maintainers": ["test_github:user-with-role"]}, "maintainer"),
        ({"members": ["test_github:user-with-role"]}, "member"),
    ],
)
def test_config_create_user_with_role(
    routed_client, db, oauth_server, config, default_role, expected_role
):

    response = routed_client.get(f'/auth/{oauth_server.provider}/authorize')

    assert response.status_code == 200

    user = db.query(User).filter(User.username == "user-with-role").one_or_none()
    assert user

    if oauth_server.provider == 'test_github':
        assert user.role == expected_role
    elif default_role:
        assert user.role == default_role
    else:
        assert user.role is None


@pytest.fixture
def channel(db):
    channel = Channel(name="user-with-role", private=True)
    db.add(channel)
    db.commit()
    return channel


@pytest.mark.parametrize("config_extra", ["[users]\ncreate_default_channel = true"])
def test_config_create_default_channel_exists(routed_client, db, oauth_server, channel):

    response = routed_client.get(f'/auth/{oauth_server.provider}/authorize')

    assert response.status_code == 200

    user = db.query(User).filter(User.username == "user-with-role").one_or_none()
    assert user

    channel = db.query(Channel).filter(Channel.name == "user-with-role").one_or_none()

    assert channel
    assert user not in [member.user for member in channel.members]

    user_channel = (
        db.query(ChannelMember).filter(ChannelMember.user_id == user.id).one_or_none()
    )

    assert user_channel

    assert user_channel.channel_name.startswith("user-with-role")


@pytest.fixture
def user(dao: Dao, db):
    user = dao.create_user_with_role("existing_user", role=SERVER_OWNER)
    yield user
    db.delete(user)
    db.commit()


@pytest.mark.parametrize("default_role", ["member", "maintainer", "owner", None])
@pytest.mark.parametrize("login", ["existing_user", "new_user"])
def test_config_user_exists(
    routed_client, db, oauth_server, channel, user, login, default_role, app
):
    profile = Profile(user=user)
    identity = Identity(
        provider=oauth_server.provider, user=user, identity_id="existing_user_id"
    )
    db.add(identity)
    db.add(profile)
    db.commit()

    response = routed_client.get(f'/auth/{oauth_server.provider}/authorize')

    assert response.status_code == 200

    db.refresh(user)

    users = db.query(User).filter(User.username == login).all()
    assert len(users) == 1

    new_user = users[0]

    assert new_user
    assert new_user.username == login
    assert login != "existing_user" or new_user.role == SERVER_OWNER
    assert login == "existing_user" or new_user.role == default_role
    assert new_user.profile
    assert new_user.identities
    assert new_user.identities[0].provider == oauth_server.provider


@pytest.fixture
def some_identity(user, db):
    identity = Identity(
        provider="some-provider", user=user, identity_id='some-identity'
    )
    db.add(identity)
    db.commit()
    yield identity
    db.delete(identity)
    db.commit()


# db will automatically rollback, so need to disable running tests in nested transaction
@pytest.mark.parametrize("auto_rollback", [False])
@pytest.mark.parametrize("login", ["existing_user"])
def test_config_user_with_identity_exists(
    routed_client,
    db,
    oauth_server,
    user,
    login,
    some_identity,
):
    # we should not be allowed to associate a social account with a user that
    # already has an identity from a different provider

    response = routed_client.get(f'/auth/{oauth_server.provider}/authorize')
    db.refresh(user)
    assert len(user.identities) == 1
    assert user.identities[0].provider == "some-provider"
    assert response.status_code == 422
