# Copyright 2020 QuantStack, Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import json
from urllib.parse import quote

import httpx

from quetz.config import Config

from .oauth2 import OAuthAuthenticator, OAuthHandlers


class JupyterhubOAuthHandlers(OAuthHandlers):
    """Handlers for authenticator endpoints"""


class JupyterhubAuthenticator(OAuthAuthenticator):
    # Register the app here: https://console.developers.google.com/apis/credentials

    provider = 'jupyterhub'
    client_id = "quetz_client"
    client_secret = "super-secret"

    access_token_url = 'http://jupyterhub:8000/hub/api/oauth2/token'
    validate_token_url = "authorizations/token/{}"
    authorize_url = 'http://localhost:8001/hub/api/oauth2/authorize'
    api_base_url = 'http://jupyterhub:8000/hub/api/'

    handler_cls = JupyterhubOAuthHandlers
    is_enabled = True

    async def userinfo(self, request, token):
        # profile = await self.client.parse_id_token(request, token)
        access_token = token["access_token"]
        response = await self._get_user_for_token(access_token)
        profile = response.json()

        github_profile = {
            "id": profile["name"],
            "name": profile["name"],
            "avatar_url": "",
            "login": profile["name"],
        }
        return github_profile

    def configure(self, config: Config):
        self.is_enabled = True

        # call the configure of base class to set default_channel and default role
        super().configure(config)

    async def _get_user_for_token(self, token):
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.api_base_url
                + self.validate_token_url.format(quote(token, safe='')),
                headers={'Authorization': 'token {}'.format(self.client_secret)},
            )
        return resp

    async def validate_token(self, token):
        access_token = json.loads(token)["access_token"]
        resp = await self._get_user_for_token(access_token)
        return resp.status_code == 200
