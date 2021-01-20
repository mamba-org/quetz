from fastapi import APIRouter, Depends, Request
from starlette.responses import RedirectResponse

from quetz.config import Config
from quetz.dao import Dao
from quetz.deps import get_config, get_dao


class AuthenticationHandlers:
    """Handlers for authenticator endpoints"""

    def __init__(self, authenticator, app=None):

        self.authenticator = authenticator

        # dependency_overrides_provider kwarg is needed for unit test
        self.router = APIRouter(
            prefix=f"/auth/{authenticator.provider}", dependency_overrides_provider=app
        )
        self.router.add_api_route("/login", self.login, methods=["GET"])
        self.router.add_api_route("/enabled", self.enabled, methods=["GET"])
        self.router.add_api_route(
            "/authorize",
            self.authorize,
            methods=["GET"],
            name=f"authorize_{authenticator.provider}",
        )
        self.router.add_api_route("/revoke", self.revoke, methods=["GET"])

    async def login(self, request: Request):
        return "<html><body><h1>Login Page</h1></body></html>"

    async def enabled(self):
        """Entrypoint used by frontend to show the login button."""
        return self.authenticator.is_enabled

    async def authorize(
        self,
        request: Request,
        dao: Dao = Depends(get_dao),
        config: Config = Depends(get_config),
    ):

        user_dict = await self.authenticator.authenticate(request, dao, config)

        request.session['user_id'] = user_dict['user_id']

        request.session['identity_provider'] = user_dict['auth_state']['provider']

        request.session['token'] = user_dict['auth_state']['token']

        resp = RedirectResponse('/')

        return resp


class BaseAuthenticator:
    """Base class for authenticators using Oauth2 protocol and its variants"""

    provider = "base"
    handler_cls = AuthenticationHandlers

    is_enabled = False

    @property
    def router(self):
        return self.handler.router

    def __init__(self, config: Config, provider=None, app=None):
        if provider is not None:
            self.provider = str(provider)
        self.handler = self.handler_cls(self, app)

        self.configure(config)

    def configure(self, config):
        raise NotImplementedError("subclasses need to implement configure")

    async def validate_token(self, token):
        return True
