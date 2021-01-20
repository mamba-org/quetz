import uuid

from fastapi import APIRouter, Depends, Request, Response
from starlette.responses import RedirectResponse

from quetz.config import Config
from quetz.dao import Dao
from quetz.deps import get_config, get_dao


class BaseAuthenticationHandlers:
    """Handlers for authenticator endpoints"""

    # list of methods that /authorize endpoint can be requested with
    authorize_methods = []

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
            methods=self.authorize_methods,
            name=f"authorize_{authenticator.provider}",
        )

    async def login(self, request: Request):
        raise NotImplementedError("method login must be implemented in subclasses")

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

        # use 303 code so that the method is always changed to GET
        resp = RedirectResponse('/', status_code=303)

        return resp


class BaseAuthenticator:
    """Base class for authenticators using Oauth2 protocol and its variants"""

    provider = "base"
    handler_cls = BaseAuthenticationHandlers

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
        return False

    async def authenticate(self, request, dao, config):
        raise NotImplementedError("subclasses need to implement authenticate")


class FormHandlers(BaseAuthenticationHandlers):

    authorize_methods = ["POST"]

    async def login(self, request: Request):
        redirect_uri = request.url_for(f'authorize_{self.authenticator.provider}')
        data = f"""
<html><body><h1>Login Page</h1>
<form method="post" action="{redirect_uri}">
  <label>username:
    <input name="username" autocomplete="name">
  </label>
  <button>Submit</button>
</form>
</body></html>"""
        return Response(content=data, media_type="text/html")


class SimpleAuthenticator(BaseAuthenticator):
    provider = "simple"
    handler_cls = FormHandlers

    def configure(self, config):
        self.is_enabled = True

    async def authenticate(self, request: Request, dao, config):
        data = await request.form()
        user = dao.get_user_by_username(data['username'])

        return {
            "user_id": str(uuid.UUID(bytes=user.id)),
            "auth_state": {"provider": self.provider, "token": "Token"},
        }
