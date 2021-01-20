# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import json
import uuid
from typing import Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request
from starlette.responses import RedirectResponse

from quetz.deps import get_config, get_dao

from .config import Config
from .dao import Dao
from .dao_github import get_user_by_github_identity


class OAuthAuthenticator:
    oauth = OAuth()
    provider = "oauth"

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

    # provider api endpoint urls
    validate_token_url: Optional[str] = None
    revoke_url: Optional[str] = None

    def __init__(self, config: Config, client_kwargs=None, provider=None, app=None):
        if provider is not None:
            self.provider = str(provider)

        self.configure(config)
        self.register(client_kwargs=client_kwargs)

        # dependency_overrides_provider kwarg is needed for unit test
        self.router = APIRouter(
            prefix=f"/auth/{self.provider}", dependency_overrides_provider=app
        )
        self.router.add_api_route("/login", self.login, methods=["GET"])
        self.router.add_api_route("/enabled", self.enabled, methods=["GET"])
        self.router.add_api_route(
            "/authorize",
            self.authorize,
            methods=["GET"],
            name=f"authorize_{self.provider}",
        )
        self.router.add_api_route("/revoke", self.revoke, methods=["GET"])

    async def login(self, request: Request):
        redirect_uri = request.url_for(f'authorize_{self.provider}')
        return await self.client.authorize_redirect(request, redirect_uri)

    def configure(self, config):
        raise NotImplementedError("subclasses need to implement configure")

    async def userinfo(self, request, token):
        raise NotImplementedError("subclasses need to implement userinfo")

    def register(self, client_kwargs=None):
        # Register the app here: https://github.com/settings/applications/new

        if client_kwargs is None:
            client_kwargs = {}

        if self.scope:
            client_kwargs["scope"] = self.scope

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
        # identity = get_identity(db, identity_id)
        resp = await self.client.get(self.validate_token_url, token=json.loads(token))
        return resp.status_code != 401

    async def enabled(self):
        """Entrypoint used by frontend to show the login button."""
        return self.is_enabled

    async def authorize(
        self,
        request: Request,
        dao: Dao = Depends(get_dao),
        config: Config = Depends(get_config),
    ):
        token = await self.client.authorize_access_token(request)
        profile = await self.userinfo(request, token)
        profile['provider'] = self.provider
        user = get_user_by_github_identity(dao, profile, config)

        request.session['user_id'] = str(uuid.UUID(bytes=user.id))

        request.session['identity_provider'] = self.provider

        request.session['token'] = json.dumps(token)

        resp = RedirectResponse('/')

        return resp

    async def revoke(self, request):
        client_id = self.client.client_id
        return RedirectResponse(self.revoke_url.format(client_id=client_id))


class GithubAuthenticator(OAuthAuthenticator):
    oauth = OAuth()
    provider = "github"

    # oauth client params
    access_token_url = 'https://github.com/login/oauth/access_token'
    authorize_url = 'https://github.com/login/oauth/authorize'
    api_base_url = 'https://api.github.com/'
    scope = 'user:email'

    # endpoint urls
    validate_token_url = "user"
    revoke_url = 'https://github.com/settings/connections/applications/{client_id}'

    async def userinfo(self, request, token):
        resp = await self.client.get('user', token=token)
        profile = resp.json()

        return profile

    def configure(self, config):
        self.client_id = config.github_client_id
        self.client_secret = config.github_client_secret
        self.is_enabled = True
