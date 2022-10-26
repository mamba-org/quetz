import sys
import uuid
from typing import Dict, List, Optional, Type, Union

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.sql.sqltypes import Boolean
from starlette.responses import RedirectResponse

from quetz.authorization import ServerRole
from quetz.config import Config
from quetz.dao import Dao
from quetz.deps import get_config, get_dao

if sys.version_info >= (3, 8):
    from typing import TypedDict  # pylint: disable=no-name-in-module
else:
    from typing_extensions import TypedDict

from . import auth_dao


class Email(TypedDict):

    email: str
    verified: Boolean
    primary: Boolean


class UserProfile(TypedDict):

    id: str
    name: str
    avatar_url: str
    login: str
    emails: List[Email]


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
            "emails": [],
        }

        profile: UserProfile = user_data.get("profile", default_profile)

        role = await self.authenticator.user_role(request, profile)
        default_channel = await self.authenticator.user_channels(request, profile)

        user = auth_dao.get_user_by_identity(
            dao, self.authenticator.provider, profile, config, role, default_channel
        )

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

    - :py:meth:`authenticate`

    Subclasses SHOULD implement:

    - :py:meth:`configure`
    - :py:meth:`validate_token`

    """

    provider = "base"
    handler_cls: Type[BaseAuthenticationHandlers] = BaseAuthenticationHandlers

    is_enabled = False

    default_role: Optional[str] = None
    default_channel: Optional[str] = None

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

        # use the config to configure default role and
        # whether to create a default channel
        if config.configured_section("users"):
            self.default_role = config.users_default_role
            self._admins = config.users_admins
            self._maintainers = config.users_maintainers
            self._members = config.users_members
            self.create_default_channel = config.users_create_default_channel
        else:
            self.default_role = None
            self.create_default_channel = False
            self._admins = []
            self._maintainers = []
            self._members = []

    async def validate_token(self, token):
        "check token validity"
        return True

    async def user_role(self, request: Request, profile: UserProfile) -> Optional[str]:
        """return default role of the new user"""
        login = profile['login']
        user_str = f"{self.provider}:{login}"

        if user_str in self._admins:
            return ServerRole.OWNER
        elif user_str in self._maintainers:
            return ServerRole.MAINTAINER
        elif user_str in self._members:
            return ServerRole.MEMBER
        else:
            return self.default_role

    async def user_channels(
        self, request: Request, profile: UserProfile
    ) -> Optional[List[str]]:
        """user channel"""
        if self.create_default_channel:
            return [profile["login"]]
        else:
            return None

    async def authenticate(
        self, request, data=None, dao=None, config=None, **kwargs
    ) -> AuthReturnType:
        """Authentication user with the data submitted.

        This method should return:

        - ``None`` if the authentication failed,
        - string with username for successful authentication
        - or a dictionary with keys ``username``, ``profile`` (user profile data),
          ``auth_state`` (extra authentication state to be stored in the browser
          session).

        """

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
    <input name="password" type="password">
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
    """A demo of a possible implementation. It redirects users to a
    simple HTML form where they can type their username and password.

    Note: Consider this an example. In your production setting you would
    probably want to redirect to your custom login page. Make sure that
    this page submits data to ``/auth/{provider}/authorize`` endpoint."""

    provider = "simple"
    handler_cls = FormHandlers

    def configure(self, config):
        self.is_enabled = True

        super().configure(config)

    async def authenticate(
        self, request: Request, data=None, dao=None, config=None, **kwargs
    ) -> Optional[str]:
        if data["username"] == data["password"]:
            return data['username']
        else:
            return None
