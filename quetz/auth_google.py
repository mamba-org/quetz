# Copyright 2020 QuantStack, Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import json
import uuid

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request
from starlette.responses import RedirectResponse

from quetz.deps import get_config, get_dao

from .auth_github import GithubAuthenticator
from .config import Config
from .dao import Dao
from .dao_google import get_user_by_google_identity


class GoogleAuthenticator(GithubAuthenticator):
    provider = 'google'
    server_metadata_url = 'https://accounts.google.com/.well-known/openid-configuration'

    def register(self, config, client_kwargs=None):
        # Register the app here: https://console.developers.google.com/apis/credentials
        if client_kwargs is None:
            client_kwargs = {}
        self.client = self.oauth.register(
            name=self.provider,
            client_id=config.google_client_id,
            client_secret=config.google_client_secret,
            server_metadata_url=self.server_metadata_url,
            client_kwargs={'scope': 'openid email profile', **client_kwargs},
            prompt='select_account',
        )

    async def validate_token(self, token):
        resp = await self.client.get(
            'https://openidconnect.googleapis.com/v1/userinfo', token=json.loads(token)
        )
        return resp.status_code != 401

    async def revoke(request):
        return RedirectResponse('https://myaccount.google.com/permissions')

    async def userinfo(self, request, token):
        profile = await self.client.parse_id_token(request, token)

        github_profile = {
            "id": profile["sub"],
            "name": profile["name"],
            "avatar_url": profile['picture'],
            "login": profile["email"],
        }
        return github_profile
