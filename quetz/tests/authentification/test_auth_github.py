import importlib
import time

import pytest
from authlib.jose import JsonWebKey, jwt
from authlib.oidc.core.util import create_half_hash

from quetz import auth_github, auth_google
from quetz.authorization import SERVER_OWNER
from quetz.dao import Dao
from quetz.db_models import Channel, ChannelMember, Identity, Profile, User
from quetz.testing.utils import AsyncPathMapDispatch


@pytest.fixture
def default_role():
    return "member"


@pytest.fixture
def config_extra(default_role):
    return f'[users]\ndefault_role = "{default_role}"\n' if default_role else ""


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

    return "github", response


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

    return "google", response


@pytest.fixture
def config_auth():
    return """
[github]
client_id = "aaa"
client_secret = "bbb"

[google]
client_id = "aaa"
client_secret = "bbb"
"""


@pytest.fixture(
    params=[
        "github_response",
        "google_response",
    ]
)
def oauth_server(request, config):
    provider, response = request.getfixturevalue(request.param)

    app = AsyncPathMapDispatch(response)

    # we need to remove the client, because it might have been already
    # registered in quetz.main

    if provider == 'github':
        auth_module = auth_github
    elif provider == "google":
        auth_module = auth_google

    # we need to reload here because we changed config and
    # some providers might not have been registered
    from quetz import main

    importlib.reload(main)
    _prev_registry_item = auth_module.oauth._registry.pop(provider, None)
    _prev_clients_item = auth_module.oauth._clients.pop(provider, None)

    auth_module.register(config, client_kwargs={'app': app})

    yield provider

    if _prev_registry_item:
        auth_module.oauth._registry[provider] = _prev_registry_item
    if _prev_clients_item:
        auth_module.oauth._clients[provider] = _prev_clients_item


@pytest.mark.parametrize("config_extra", ["[users]\ncreate_default_channel = true"])
def test_config_create_default_channel(client, db, oauth_server, config):

    response = client.get(f'/auth/{oauth_server}/authorize')

    assert response.status_code == 200

    user = db.query(User).filter(User.username == "user-with-role").one_or_none()
    assert user

    channel = db.query(Channel).filter(Channel.name == "user-with-role").one_or_none()

    assert channel
    assert user == channel.members[0].user


@pytest.fixture
def channel(db):
    channel = Channel(name="user-with-role", private=True)
    db.add(channel)
    db.commit()
    return channel


@pytest.mark.parametrize("config_extra", ["[users]\ncreate_default_channel = true"])
def test_config_create_default_channel_exists(client, db, oauth_server, channel):

    response = client.get(f'/auth/{oauth_server}/authorize')

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
def user(dao: Dao):
    return dao.create_user_with_role("existing_user", role=SERVER_OWNER)


@pytest.mark.parametrize("default_role", ["member", "maintainer", "owner", None])
@pytest.mark.parametrize("login", ["existing_user", "new_user"])
def test_config_user_exists(
    client, db, oauth_server, channel, user, config, login, default_role
):
    profile = Profile(user=user)
    identity = Identity(
        provider=oauth_server, user=user, identity_id="existing_user_id"
    )
    db.add(identity)
    db.add(profile)

    response = client.get(f'/auth/{oauth_server}/authorize')

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
    assert new_user.identities[0].provider == oauth_server


@pytest.mark.parametrize("provider", ["dummy", "github", "google"])
@pytest.mark.parametrize("login", ["existing_user"])
def test_config_user_with_identity_exists(
    client, db, oauth_server, channel, user, config, login, default_role, provider
):
    # we should not be allowed to associate a social account with a user that
    # already has an identity from a different provider
    identity = Identity(provider=provider, user=user, identity_id='some-identity')
    db.add(identity)

    response = client.get(f'/auth/{oauth_server}/authorize')
    db.refresh(user)
    assert len(user.identities) == 1
    assert user.identities[0].provider == provider
    assert response.status_code == 422
