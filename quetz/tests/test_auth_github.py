import json

import pytest
from starlette.requests import Request as ASGIRequest
from starlette.responses import Response as ASGIResponse

from quetz import auth_github
from quetz.db_models import User


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
    return f"""[users]
default_role = "{default_role}"
"""


@pytest.fixture
def oauth_server(config):

    app = AsyncPathMapDispatch(
        {
            '/login/oauth/access_token': {'body': {'access_token': 'b'}},
            '/user': {
                "body": {
                    "login": "user_with_role",
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


@pytest.mark.parametrize("default_role", ["member", "maintainer", "owner"])
def test_github_oauth(client, db, oauth_server, default_role):

    response = client.get('/auth/github/authorize')

    assert response.status_code == 200

    user = db.query(User).filter(User.username == "user_with_role").one_or_none()
    assert user
    assert user.role == default_role


@pytest.mark.parametrize("config_extra", [""])
def test_config_without_default_role(client, db, oauth_server):

    response = client.get('/auth/github/authorize')

    assert response.status_code == 200

    user = db.query(User).filter(User.username == "user_with_role").one_or_none()
    assert user
    assert user.role is None
