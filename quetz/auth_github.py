# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import json
import uuid

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request
from starlette.responses import RedirectResponse

from quetz.deps import get_config, get_dao

from .config import Config
from .dao import Dao
from .dao_github import get_user_by_github_identity


class GithubAuthenticator:
    oauth = OAuth()

    def __init__(self, provider: str, config: Config, client_kwargs=None):
        self.register(config, client_kwargs=client_kwargs)
        self.router = APIRouter(prefix=f"/auth/{provider}")
        self.router.add_api_route("/login", self.login, methods=["GET"])
        self.router.add_api_route("/enabled", self.enabled, methods=["GET"])
        self.router.add_api_route(
            "/authorize", self.authorize, methods=["GET"], name="authorize_github"
        )
        self.router.add_api_route("/revoke", self.revoke, methods=["GET"])

    async def login(self, request: Request):
        github = self.oauth.create_client('github')
        redirect_uri = request.url_for('authorize_github')
        return await github.authorize_redirect(request, redirect_uri)

    def register(self, config, client_kwargs=None):
        # Register the app here: https://github.com/settings/applications/new

        if client_kwargs is None:
            client_kwargs = {}

        self.oauth.register(
            name="github",
            client_id=config.github_client_id,
            client_secret=config.github_client_secret,
            access_token_url='https://github.com/login/oauth/access_token',
            access_token_params=None,
            authorize_url='https://github.com/login/oauth/authorize',
            authorize_params=None,
            api_base_url='https://api.github.com/',
            client_kwargs={'scope': 'user:email', **client_kwargs},
        )

    async def validate_token(self, token):
        # identity = get_identity(db, identity_id)
        resp = await self.oauth.github.get('user', token=json.loads(token))
        return resp.status_code != 401

    async def enabled(self):
        """Entrypoint used by frontend to show the login button."""
        return True

    async def authorize(
        self,
        request: Request,
        dao: Dao = Depends(get_dao),
        config: Config = Depends(get_config),
    ):
        token = await self.oauth.github.authorize_access_token(request)
        resp = await self.oauth.github.get('user', token=token)
        profile = resp.json()
        user = get_user_by_github_identity(dao, profile, config)

        request.session['user_id'] = str(uuid.UUID(bytes=user.id))

        request.session['identity_provider'] = 'github'

        request.session['token'] = json.dumps(token)

        resp = RedirectResponse('/')

        return resp

    async def revoke(self, request):
        client_id = self.oauth.github.client_id
        return RedirectResponse(
            f'https://github.com/settings/connections/applications/{client_id}'
        )
