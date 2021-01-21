import uuid
from typing import Dict, List, Optional, Type, TypedDict, Union

from fastapi import APIRouter, Depends, Request, Response
from starlette.responses import RedirectResponse

from quetz.config import Config
from quetz.dao import Dao
from quetz.deps import get_config, get_dao

from .auth_dao import get_user_by_identity


class UserProfile(TypedDict):

    id: str
    name: str
    avatar_url: str
    login: str


class UserName(TypedDict):
    username: str


class UserDict(UserName, total=False):
    # profile and auth_state keys are optional
    profile: UserProfile
    auth_state: Dict[str, str]


AuthReturnType = Optional[Union[str, UserDict]]


class BaseAuthenticationHandlers:
    """Handlers for authenticator endpoints.

    Subclasses MUST implement:

    - login method
    - authorize_methods: provide allowed HTTP methods for authorize endpoint

    SHOULD override:

    - _authenticate method - to extract data and past it to
      BaseAuthenticator.authenticate method
    """

    # list of methods that /authorize endpoint can be requested with
    authorize_methods: List[str]

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
        """{prefix}/login endpoint
        First entry point to trigger login process"""
        raise NotImplementedError("method login must be implemented in subclasses")

    async def enabled(self):
        """{prefix}/enabled endpoint
        Used by frontend to show the login button."""

        return self.authenticator.is_enabled

    async def authorize(
        self,
        request: Request,
        dao: Dao = Depends(get_dao),
        config: Config = Depends(get_config),
    ):
        """{prefix}/authorize endpoint
        Entry point for user submitted data or callback for oauth applications.

        To configure HTTP method that this endpoint will handle, set authorize_methods.
        """

        user_dict = await self._authenticate(request, dao, config)

        if user_dict is None:
            return Response("login failed")

        if isinstance(user_dict, str):
            # wrap string in a dictionary
            user_data: UserDict = {"username": user_dict}
        else:
            user_data = user_dict

        default_profile: UserProfile = {
            "login": user_data["username"],
            "id": user_data["username"],
            "name": user_data["username"],
            "avatar_url": "",
        }

        profile: UserProfile = user_data.get("profile", default_profile)

        user = get_user_by_identity(dao, profile, config)

        user_id = str(uuid.UUID(bytes=user.id))

        request.session['user_id'] = user_id
        request.session['identity_provider'] = self.authenticator.provider
        request.session.update(user_data.get("auth_state", {}))

        # use 303 code so that the method is always changed to GET
        resp = RedirectResponse('/', status_code=303)

        return resp

    async def _authenticate(self, request, dao, config) -> AuthReturnType:
        """wrapper around `authenticate` method of the Authenticator subclasses

        mainly used to extract data from request."""

        user_dict = await self.authenticator.authenticate(
            request, data=None, dao=dao, config=config
        )
        return user_dict


class BaseAuthenticator:
    """Base class for authenticators.

    Subclasses MUST implement:

    - configure
    - authenticate

    Subclasses SHOULD implement:

    - validate_token
    """

    provider = "base"
    handler_cls: Type[BaseAuthenticationHandlers] = BaseAuthenticationHandlers

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
        """configure authenticator and set is_enabled=True"""
        raise NotImplementedError("subclasses need to implement configure")

    async def validate_token(self, token):
        "check token validity"
        return True

    async def authenticate(
        self, request, data=None, dao=None, config=None, **kwargs
    ) -> AuthReturnType:
        """return username or dictionary with keys 'username', 'profile', 'auth_state'.
        See type annotation for detail.

        Return None if login credentials are not correct"""
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
  <label>password:
    <input name="password" autocomplete="name">
  </label>
  <button>Submit</button>
</form>
</body></html>"""
        return Response(content=data, media_type="text/html")

    async def _authenticate(self, request, dao, config):
        """Wrapper around `authenticate` method of the Authenticator subclasses.

        Extracts form data from request."""

        data = await request.form()

        user_dict = await self.authenticator.authenticate(
            request, data=data, dao=dao, config=config
        )

        return user_dict


class SimpleAuthenticator(BaseAuthenticator):
    """A demo of a possible implementation.

    NOT FOR USE IN PRODUCTION."""

    provider = "simple"
    handler_cls = FormHandlers

    def configure(self, config):
        self.is_enabled = True

    async def authenticate(
        self, request: Request, data=None, dao=None, config=None, **kwargs
    ) -> Optional[str]:
        if data["username"] == data["password"]:
            return data['username']
        else:
            return None
