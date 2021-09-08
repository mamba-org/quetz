import time

import pytest
from authlib.jose import JsonWebKey, jwt
from authlib.oidc.core.util import create_half_hash
from fastapi.testclient import TestClient

from quetz.authentication import github as auth_github
from quetz.authentication import google as auth_google
from quetz.authentication.azuread import AzureADAuthenticator
from quetz.authentication.jupyterhub import JupyterhubAuthenticator
from quetz.authorization import SERVER_OWNER
from quetz.dao import Dao
from quetz.db_models import Channel, ChannelMember, Identity, Profile, User
from quetz.testing.utils import AsyncPathMapDispatch


@pytest.fixture
def default_role():
    return "member"


@pytest.fixture
def user_group():
    return None


@pytest.fixture
def user_roles(provider_spec, login, user_group):
    # add user login identified with provider provider_spec to
    # group user_group
    provider_name, _ = provider_spec
    roles = {"admins": [], "members": [], "maintainers": []}

    if user_group:
        roles[user_group].append(f"{provider_name}:{login}")
    return roles


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
def github_response(login):

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
def azuread_response(login):
    response = {
        '/3cd6563a-bbcf-4e30-bbc6-ea3445c75c79/oauth2/v2.0/token': {
            'body': {'access_token': 'b'}
        },
        '/oidc/userinfo': {
            "body": {
                'sub': login + '_id',
                'name': 'monalisa',
                'family_name': 'Lisa',
                'given_name': 'Mona',
                'picture': 'https://graph.microsoft.com/v1.0/me/photo/$value',
                'email': login,
            }
        },
        '/3cd6563a-bbcf-4e30-bbc6-ea3445c75c79/v2.0/.well-known/openid-configuration': {
            "body": {
                "token_endpoint": "https://login.microsoftonline.com/"
                "3cd6563a-bbcf-4e30-bbc6-ea3445c75c79/oauth2/v2.0/token",
                "token_endpoint_auth_methods_supported": [
                    "client_secret_post",
                    "private_key_jwt",
                    "client_secret_basic",
                ],
                "jwks_uri": "https://login.microsoftonline.com/"
                "3cd6563a-bbcf-4e30-bbc6-ea3445c75c79/discovery/v2.0/keys",
                "response_modes_supported": ["query", "fragment", "form_post"],
                "subject_types_supported": ["pairwise"],
                "id_token_signing_alg_values_supported": ["RS256"],
                "response_types_supported": [
                    "code",
                    "id_token",
                    "code id_token",
                    "id_token token",
                ],
                "scopes_supported": ["openid", "profile", "email", "offline_access"],
                "issuer": "https://login.microsoftonline.com/"
                "3cd6563a-bbcf-4e30-bbc6-ea3445c75c79/v2.0",
                "request_uri_parameter_supported": False,
                "userinfo_endpoint": "https://graph.microsoft.com/oidc/userinfo",
                "authorization_endpoint": "https://login.microsoftonline.com/"
                "3cd6563a-bbcf-4e30-bbc6-ea3445c75c79/oauth2/v2.0/authorize",
                "device_authorization_endpoint": "https://login.microsoftonline.com/"
                "3cd6563a-bbcf-4e30-bbc6-ea3445c75c79/oauth2/v2.0/devicecode",
                "http_logout_supported": True,
                "frontchannel_logout_supported": True,
                "end_session_endpoint": "https://login.microsoftonline.com/"
                "3cd6563a-bbcf-4e30-bbc6-ea3445c75c79/oauth2/v2.0/logout",
                "claims_supported": [
                    "sub",
                    "iss",
                    "cloud_instance_name",
                    "cloud_instance_host_name",
                    "cloud_graph_host_name",
                    "msgraph_host",
                    "aud",
                    "exp",
                    "iat",
                    "auth_time",
                    "acr",
                    "nonce",
                    "preferred_username",
                    "name",
                    "tid",
                    "ver",
                    "at_hash",
                    "c_hash",
                    "email",
                ],
                "kerberos_endpoint": "https://login.microsoftonline.com/"
                "3cd6563a-bbcf-4e30-bbc6-ea3445c75c79/kerberos",
                "tenant_region_scope": "EU",
                "cloud_instance_name": "microsoftonline.com",
                "cloud_graph_host_name": "graph.windows.net",
                "msgraph_host": "graph.microsoft.com",
                "rbac_url": "https://pas.windows.net",
            }
        },
    }

    return "test_azuread", response


@pytest.fixture
def jupyter_response(login):

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


GOOGLE_CERT = """-----BEGIN CERTIFICATE-----
MIIDazCCAlOgAwIBAgIUHFhnnOpbCrKVxDGjpRBhXMolH/kwDQYJKoZIhvcNAQEL
BQAwRTELMAkGA1UEBhMCQVUxEzARBgNVBAgMClNvbWUtU3RhdGUxITAfBgNVBAoM
GEludGVybmV0IFdpZGdpdHMgUHR5IEx0ZDAeFw0yMTAxMTgxNDI4NTJaFw0yNDAx
MTgxNDI4NTJaMEUxCzAJBgNVBAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEw
HwYDVQQKDBhJbnRlcm5ldCBXaWRnaXRzIFB0eSBMdGQwggEiMA0GCSqGSIb3DQEB
AQUAA4IBDwAwggEKAoIBAQDH/ZUbewS+Tukx50UjRZ4bWij1tzoaQTo1NDWCwv7S
OGKY083dFR567aag1rhUHjiniuf8UVv935Ydq4VWmwV6N6XHoSLNXQSHcAN7VFos
We5ENAfBz4JmfZnZfG+QBB0nGtd7hjE/xtOUsOhuzposi8fP+FXwPMVMmgfuWS6Z
1SNODuwmtwobhe7x8ez6l70lWUIhac5SAQwUicsdqlH1gBFkcGMmFRj9DrslpYvu
8bq1UcGE3NhzHkIo4ssAE2NlHtzbDnxYpXGC3aEPtWHL/mFVneud2a6ZcEVDc1Nq
cwcWliUwK6FI/wVcNYbCX6AozSor2+XCtUTyXdGoj+spAgMBAAGjUzBRMB0GA1Ud
DgQWBBRV8o2cbHAis+yj0dzP1j25bCOjkjAfBgNVHSMEGDAWgBRV8o2cbHAis+yj
0dzP1j25bCOjkjAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUAA4IBAQAA
8fT4OiTn1zPBBV702LP3cxJd+iOtfTxBFTOB9QATYpKmaQvgf6gRLHgzgFJSpn0e
e/NH9wEllLqwbZbmz9kOH/LxaY8WD8eWbWTR0+2dcaxG0qjitlijnHfEsVANvv9O
FK+exD3aCdMK/WUr5Shae2jRhDzLcGYdMeCD9Nxc1ShmHDA/4eUqk+SOso+O5v6i
ZqmzBWk/u9Z7JvQ41R0OG1tJoNrD02ctH2lel/ZX/7Ff4HxK6QyzBNtEnvJBXy/R
3qXwz4/xMdlqU0GKGpYLBvm180Nvmuohdtvzt8A8/nUKyNDJwzLHp7BjoyK9JxYy
xT/6TQKFDnCKt1Mzg1Py
-----END CERTIFICATE-----"""

GOOGLE_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEAx/2VG3sEvk7pMedFI0WeG1oo9bc6GkE6NTQ1gsL+0jhimNPN
3RUeeu2moNa4VB44p4rn/FFb/d+WHauFVpsFejelx6EizV0Eh3ADe1RaLFnuRDQH
wc+CZn2Z2XxvkAQdJxrXe4YxP8bTlLDobs6aLIvHz/hV8DzFTJoH7lkumdUjTg7s
JrcKG4Xu8fHs+pe9JVlCIWnOUgEMFInLHapR9YARZHBjJhUY/Q67JaWL7vG6tVHB
hNzYcx5CKOLLABNjZR7c2w58WKVxgt2hD7Vhy/5hVZ3rndmumXBFQ3NTanMHFpYl
MCuhSP8FXDWGwl+gKM0qK9vlwrVE8l3RqI/rKQIDAQABAoIBAB48JDLHYmwzGeZF
hJpUiBayhsa/MLWPbvFkN0LRoBzAEYfxXYozCyyiiTJ/w9ZTy1TpFzF6S2IST2uk
5r+1KBrWFuYbYluR2IFxWdVnZ0qVPgRpqVKPwLMmAgBzY5puRMoIsNMn8oIl2Q79
v+YgrgZWC5tRfAyZ42o1T0WljfoLjqImry1gEFpfmKXmoKbcJhd0fTfobuG6lxY6
fkySEDeYuq4t15bjSBzqgzLD7fqSRS55yukUpSucQETB/grtLykVdHFAXP/KHWy3
06Mj3oJAciHTwmIKV0+9QgTU77bYAupLaRX6/pgpLSXt9XUwbI0/I+xq8Fo8RBrt
uxtCFgECgYEA5cideXxexpc3zXjg3dkC9x4ktVh4LHyQp/Ua+kRQDvHtf7E/44Bd
GDpQnxrJ3jfhyXfdLshlI8EouT7STyC0cjtmME5WhleGBokAvdp8EEuGpArCR8iK
1uKiFzUvszv2brr50K6s6/YPaRIGbQTFLfs7hZQYXjabx2PXwHmqJ1kCgYEA3s7J
x07mHqkz56k/MONyVUhaW+PFvUTqolGe3D3nULd7XBbOX3yCzZjRVHBfBKv/Tyqs
CWl9BZy8SBZX7ieiEO+5xX2bypfUxGeWznYJoYs+RDW5vEfnxFVvJ7KD/8lqq4WC
0YY/PGziCah2iCQumypFB51FUXbljEDcGxROOFECgYEAkxu1nYI/FvrW0efyZnU5
jcWxkJv8C9cPsUedJt43Nuoxt49drKOQdiNXXBUFagvytE3Vv86x2YsfLEGI2PnC
LGPUz1ZH1KgR+PsbC3Dl/nSr1TfCG7zLDjl3tk3ppODdqxRvPOenc0VLpmPQ01i7
d+2gtKsUUrS5VJSaGvKJObkCgYEAzuWlV6+7XvNuYIu4QzSiAfGa/sNG5tetLieu
5gOR3lFTexMudlrPuA1VLRzgDx2Mij4s3NyZHPILoMEmy97/zsxdbLeUSI+vIuay
kmvny5vaqUpefCklXhqbinhpvMeTh00GSnxoEjtltuQ5lXhL0whwa36uVNScmh3M
hlTXwdECgYAwqpJKC2Ls7i+3lSPomCNK1VtbVZzfHl1YrNy7y2Eo8DsFkcnHWZJ+
qPCpHZ4sbgfziCRxOaGa+1kOXjhgXITPA/tkkhh4cglOvhHNBEVzdfHBMDxZd3HF
mD1rl6xev7GRoqUYdKYdt9NJyDGEULZ6NbIWyXo3kTp7HdQLRn0BJg==
-----END RSA PRIVATE KEY-----
"""


@pytest.fixture
def google_response(login):

    google_client_id = 'aaa'
    key = GOOGLE_PRIVATE_KEY
    cert = GOOGLE_CERT

    user_claims = {
        "picture": "http://avatar",
        "name": "monalisa",
    }
    access_token = "b"
    payload = {
        "iss": "https://accounts.google.com",
        "azp": google_client_id,
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

[azuread]
client_id = "aaa"
client_secret = "bbb"
tenant_id = "3cd6563a-bbcf-4e30-bbc6-ea3445c75c79"
"""


@pytest.fixture(
    params=[
        "github_response",
        "google_response",
        "jupyter_response",
        "azuread_response",
    ]
)
def provider_spec(request):
    provider, response = request.getfixturevalue(request.param)
    return provider, response


@pytest.fixture
def oauth_server(request, config, app, provider_spec):
    provider, response = provider_spec

    server_app = AsyncPathMapDispatch(response)

    # we need to remove the client, because it might have been already
    # registered in quetz.main

    if provider == 'test_github':
        auth_module = auth_github.GithubAuthenticator
    elif provider == "test_google":
        auth_module = auth_google.GoogleAuthenticator
    elif provider == 'test_jupyter':
        auth_module = JupyterhubAuthenticator
    elif provider == 'test_azuread':
        auth_module = AzureADAuthenticator
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
    "user_group,expected_role",
    [
        ("admins", "owner"),
        ("maintainers", "maintainer"),
        ("members", "member"),
        (None, None),
    ],
)
def test_config_create_user_with_role(
    routed_client, db, oauth_server, config, default_role, expected_role, login
):

    response = routed_client.get(f'/auth/{oauth_server.provider}/authorize')

    assert response.status_code == 200

    user = db.query(User).filter(User.username == login).one_or_none()
    assert user

    if expected_role:
        assert user.role == expected_role
    elif default_role:
        assert user.role == default_role
    else:
        assert user.role is None


@pytest.mark.parametrize("default_role", [None, 'member'])
@pytest.mark.parametrize("user_roles", [{"admins": ["other_provider:user-with-role"]}])
def test_config_create_user_with_role_in_different_provider(
    routed_client, db, oauth_server, config, default_role, login
):
    # if the user logins from a different provider than the one specified
    # in config, default_role should be assumed

    response = routed_client.get(f'/auth/{oauth_server.provider}/authorize')

    assert response.status_code == 200

    user = db.query(User).filter(User.username == login).one_or_none()
    assert user

    if default_role:
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
