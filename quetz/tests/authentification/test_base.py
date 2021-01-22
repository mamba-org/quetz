import pytest
from fastapi import Request, Response
from starlette.testclient import TestClient

from quetz.authentication.base import BaseAuthenticationHandlers, BaseAuthenticator


class DummyHandlers(BaseAuthenticationHandlers):
    authorize_methods = ["POST"]

    async def login(self, request: Request):
        return Response("success")


class DummyAuthenticator(BaseAuthenticator):

    handler_cls = DummyHandlers
    provider = 'testprovider'

    def configure(self, config):
        self.is_enabled = True

    async def authenticate(self, request, data, **kwargs):
        return "dummy-user"


@pytest.fixture
def dummy_authenticator(app, config):

    from quetz.main import auth_registry

    authenticator = DummyAuthenticator(config)

    auth_registry.register(authenticator)

    return authenticator


def test_login_endpoint(app, dummy_authenticator):

    client = TestClient(app)

    response = client.get(f"/auth/{dummy_authenticator.provider}/login")

    assert response.status_code == 200
    assert response.text == "success"
