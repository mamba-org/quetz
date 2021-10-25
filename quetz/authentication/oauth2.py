# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import json
from typing import Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import Request
from starlette.responses import RedirectResponse

from quetz.config import Config

from .base import BaseAuthenticationHandlers, BaseAuthenticator


class OAuthHandlers(BaseAuthenticationHandlers):
    """Handlers for authenticator endpoints"""

    authorize_methods = ["GET"]

    def __init__(self, authenticator, app=None):

        super().__init__(authenticator, app)

        self.router.add_api_route("/revoke", self.revoke, methods=["GET"])

    async def login(self, request: Request):
        redirect_uri = request.url_for(f'authorize_{self.authenticator.provider}')
        return await self.authenticator.client.authorize_redirect(request, redirect_uri)

    async def revoke(self, request):
        client_id = self.client.client_id
        return RedirectResponse(self.revoke_url.format(client_id=client_id))


class OAuthAuthenticator(BaseAuthenticator):
    """Base class for authenticators using Oauth2 protocol and its variants.

    The :py:meth:`authenticate` method is already implemented, but you will need to
    override some of the following variables in sublasses to make it work:

    :var str provider: name of the provider (it will be used in the url)
    :var handler_cls: class with handlers for all oauth2
      relevant endpoints in Quetz server
    :type handler_cls: sublass of :py:class:`OauthHandlers`
    :var client_id: required, client id registered with the provider
    :var client_secret: required, likewise
    :var bool is_enabled: True if authenticator is enabled, can be configured in
      :py:meth:`configure` method

    :var access_token_url: URL of the OAuth2 endpoint ot request a token
    :var authorize_url: URL of the OAuth2 ``authorize`` endpoint
    :var api_base_url: URL of the API root of the provider server
    :var validate_token_url: path of endpoint to validate the token

    """

    oauth = OAuth()
    provider = "oauth"
    handler_cls = OAuthHandlers

    # client credentials and state
    # they can be also set in configure method
    client_id: str = ""
    client_secret: str = ""
    is_enabled = False

    # oauth client params
    access_token_url: Optional[str] = None
    authorize_url: Optional[str] = None
    api_base_url: Optional[str] = None
    scope: Optional[str] = None
    server_metadata_url: Optional[str] = None
    prompt: Optional[str] = None
    client_kwargs: dict = {}

    # provider's api endpoint urls
    validate_token_url: Optional[str] = None
    revoke_url: Optional[str] = None

    @property
    def router(self):
        return self.handler.router

    def __init__(self, config: Config, client_kwargs=None, provider=None, app=None):
        super().__init__(config, provider, app)
        if self.is_enabled:
            self.register(client_kwargs=client_kwargs)

    async def userinfo(self, request, token):
        raise NotImplementedError("subclasses need to implement userinfo")

    async def authenticate(self, request, data=None, dao=None, config=None):
        token = await self.client.authorize_access_token(request)

        profile = await self.userinfo(request, token)

        username = profile["login"]
        auth_state = {"token": json.dumps(token), "provider": self.provider}

        return {"username": username, "profile": profile, "auth_state": auth_state}

    def register(self, client_kwargs=None):

        if client_kwargs is None:
            client_kwargs = {}

        if self.scope:
            client_kwargs["scope"] = self.scope

        client_kwargs.update(self.client_kwargs)

        self.client = self.oauth.register(
            name=self.provider,
            client_id=self.client_id,
            client_secret=self.client_secret,
            access_token_url=self.access_token_url,
            authorize_url=self.authorize_url,
            api_base_url=self.api_base_url,
            server_metadata_url=self.server_metadata_url,
            prompt=self.prompt,
            client_kwargs=client_kwargs,
        )

    async def validate_token(self, token):
        try:
            resp = await self.client.get(
                self.validate_token_url, token=json.loads(token)
            )
            return resp.status_code != 401
        except Exception:
            return False
