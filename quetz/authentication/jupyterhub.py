# Copyright 2020 QuantStack, Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import json
from typing import Any, List, overload
from urllib.parse import quote

import httpx

from quetz.config import Config, ConfigEntry, ConfigSection

from .oauth2 import OAuthAuthenticator


class JupyterConfigEntry:

    config_section = "jupyterhubauthenticator"
    registered_entries: List[ConfigEntry] = []
    config = None

    def __init__(self, dtype, default=None, required=True):
        self.dtype = dtype
        self.default = default
        self.required = required

    # these type annotations dont work yet, but I leave them for now
    # maybe someone will find a solution later
    # https://github.com/python/mypy/issues/2566#issuecomment-703998877
    @overload
    def __get__(self, instance: None, owner: Any) -> "JupyterConfigEntry":
        ...

    @overload
    def __get__(self, instance: object, owner: Any) -> str:
        ...

    def __get__(self, obj, objtype) -> str:
        return getattr(self.config, self.config_attr_name)

    def __set_name__(self, owner, name):
        self.attr_name = name
        self.config_attr_name = f"{self.config_section}_{name}"
        entry = ConfigEntry(
            name, self.dtype, default=self.default, required=self.required
        )
        self.registered_entries.append(entry)

    @classmethod
    def _make_config(cls):
        section = ConfigSection(
            cls.config_section,
            cls.registered_entries,
            required=False,
        )
        return [section]

    @classmethod
    def register(cls, config: Config):
        cls.config = config
        config_options = cls._make_config()
        config.register(config_options)
        return config.configured_section(cls.config_section)


class JupyterhubAuthenticator(OAuthAuthenticator):

    provider = 'jupyterhub'

    # TODO: need to figure out how to use type annotations with descriptors
    # see also: https://github.com/python/mypy/pull/2266

    client_id = JupyterConfigEntry(str, required=True)  # type: ignore
    client_secret = JupyterConfigEntry(str, required=True)  # type: ignore

    access_token_url = JupyterConfigEntry(str, required=True)  # type: ignore
    validate_token_url = "authorizations/token/{}"
    authorize_url = JupyterConfigEntry(str, required=True)  # type: ignore
    api_base_url = JupyterConfigEntry(str, required=True)  # type: ignore

    client_kwargs = {"token_endpoint_auth_method": "client_secret_post"}

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

    def configure(self, config: Config):

        self.is_enabled = JupyterConfigEntry.register(config)

        super().configure(config)
