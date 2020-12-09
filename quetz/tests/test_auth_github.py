import json

import pytest
from starlette.requests import Request as ASGIRequest
from starlette.responses import Response as ASGIResponse

from quetz import auth_github
from quetz.authorization import SERVER_OWNER
from quetz.dao import Dao
from quetz.db_models import Channel, ChannelMember, User


class AsyncPathMapDispatch:
    # dummy server, copied from authlib tests
    def __init__(self, path_maps):
        self.path_maps = path_maps

    async def __call__(self, scope, receive, send):
        request = ASGIRequest(scope, receive=receive)

        rv = self.path_maps[request.url.path]
        status_code = rv.get('status_code', 200)
        body = rv.get('body')
        headers = rv.get('headers', {})
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        else:
            if isinstance(body, str):
                body = body.encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'

        response = ASGIResponse(
            status_code=status_code,
            content=body,
            headers=headers,
        )
        await response(scope, receive, send)


@pytest.fixture
def default_role():
    return "member"


@pytest.fixture
def config_extra(default_role):
    return f'[users]\ndefault_role = "{default_role}"\n' if default_role else ""


@pytest.fixture
def login():
    return "user_with_role"


@pytest.fixture
def oauth_server(config, login):

    app = AsyncPathMapDispatch(
        {
            '/login/oauth/access_token': {'body': {'access_token': 'b'}},
            '/user': {
                "body": {
                    "login": login,
                    "avatar_url": "",
                    "id": 1,
                    "name": "monalisa",
                }
            },
        }
    )
    # we need to remove the client, because it might have been already
    # registered in quetz.main
    _prev_registry_item = auth_github.oauth._registry.pop("github")
    _prev_clients_item = auth_github.oauth._clients.pop("github")
    auth_github.register(config, client_kwargs={'app': app})

    yield

    auth_github.oauth._registry["github"] = _prev_registry_item
    auth_github.oauth._clients["github"] = _prev_clients_item


@pytest.mark.parametrize("config_extra", ["[users]\ncreate_default_channel = true"])
def test_config_create_default_channel(client, db, oauth_server):

    response = client.get('/auth/github/authorize')

    assert response.status_code == 200

    user = db.query(User).filter(User.username == "user_with_role").one_or_none()
    assert user

    channel = db.query(Channel).filter(Channel.name == "user_with_role").one_or_none()

    assert channel
    assert user == channel.members[0].user


@pytest.fixture
def channel(db):
    channel = Channel(name="user_with_role", private=True)
    db.add(channel)
    db.commit()
    return channel


@pytest.mark.parametrize("config_extra", ["[users]\ncreate_default_channel = true"])
def test_config_create_default_channel_exists(client, db, oauth_server, channel):

    response = client.get('/auth/github/authorize')

    assert response.status_code == 200

    user = db.query(User).filter(User.username == "user_with_role").one_or_none()
    assert user

    channel = db.query(Channel).filter(Channel.name == "user_with_role").one_or_none()

    assert channel
    assert user not in [member.user for member in channel.members]

    user_channel = (
        db.query(ChannelMember).filter(ChannelMember.user_id == user.id).one_or_none()
    )

    assert user_channel

    assert user_channel.channel_name.startswith("user_with_role")


@pytest.fixture
def user(dao: Dao):
    return dao.create_user_with_role("existing_user", role=SERVER_OWNER)


@pytest.mark.parametrize("default_role", ["member", "maintainer", "owner", None])
@pytest.mark.parametrize("login", ["existing_user", "new_user"])
def test_config_user_exists(
    client, db, oauth_server, channel, user, config, login, default_role
):

    assert not user.profile
    assert not user.identities

    response = client.get('/auth/github/authorize')

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
    assert new_user.identities[0].provider == 'github'
