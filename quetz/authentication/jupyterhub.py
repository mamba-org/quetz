# Copyright 2020 QuantStack, Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import json
from typing import Any, List, overload
from urllib.parse import quote

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
    """Use Oauth2 protcol to authenticate with jupyterhub server, which acts
    as identity provider.

    To activate add the following section to the ``config.toml`` (see :ref:`configfile`):

    .. code::

      [jupyterhubauthenticator]

      # client credentials, they need to be registered with
      # jupyterhub by adding an external service
      client_id = "quetz_client"
      client_secret = "super-secret"

      # token enpoint of Jupyterhub, needs to be accessible from Quetz server
      access_token_url = "http://JUPYTERHUB_HOST:PORT/hub/api/oauth2/token"

      # authorize endpoint of JupyterHub, needs to be accessible from users' browser
      authorize_url = "http://JUPYTERHUB_HOST:PORT/hub/api/oauth2/authorize"

      # API root, needs to be accesible from Quetz server
      api_base_url = "http://JUPYTERHUB_HOST:PORT/hub/api/"

    To configure quetz as an oauth client in JupyterHub, you will need to define
    a `JupyterHub service <https://jupyterhub.readthedocs.io/en/stable/reference/services.html#externally-managed-services>`_. You can achieve it by adding the following to the
    ``jupyterhub_config.py`` file of your JupyterHub instance:

    .. code::

      c.JupyterHub.services = [
          {
              # service name, it will be used to setup routers
              'name': 'quetz',
              # quetz URL to setup redirections, only required if you use
              # JupyterHub url scheme
              'url': 'http://QUETZ_HOST:PORT',
              # any secret >8 characters, you will also need to set
              # the client_secret in the authenticator config with this
              # string
              'api_token': 'super-secret',
              # client_id in the authenticator config
              'oauth_client_id': 'quetz_client',
              # URL of the callback endpoint on the quetz server
              'oauth_redirect_uri': 'http://QUETZ_HOST:PORT/auth/jupyterhub/authorize',
          }
      ]
    """  # noqa

    provider = 'jupyterhub'

    # TODO: need to figure out how to use type annotations with descriptors
    # see also: https://github.com/python/mypy/pull/2266

    client_id = JupyterConfigEntry(str, required=True)  # type: ignore
    client_secret = JupyterConfigEntry(str, required=True)  # type: ignore

    access_token_url = JupyterConfigEntry(str, required=True)  # type: ignore
    validate_token_url = "authorizations/token/{}"
    authorize_url = JupyterConfigEntry(str, required=True)  # type: ignore
    api_base_url = JupyterConfigEntry(str, required=True)  # type: ignore

    client_kwargs = {
        "token_endpoint_auth_method": "client_secret_post",
        "token_placement": "uri",
    }

    async def userinfo(self, request, token):
        response = await self._get_user_for_token(token)
        profile = response.json()

        github_profile = {
            "id": profile["name"] + '_id',
            "name": profile["name"],
            "avatar_url": "",
            "login": profile["name"],
        }
        return github_profile

    async def _get_user_for_token(self, token):
        headers = {'Authorization': 'token {}'.format(self.client_secret)}
        access_token = quote(token['access_token'], safe='')

        # authlib client will be place token in query params
        # which are ignored by jupyterhub
        # this workaround is required to implement jupyterhub API
        # which puts the token as path parameter
        # https://jupyterhub.readthedocs.io/en/stable/_static/rest-api/index.html#path--authorizations-token--token-  # noqa
        resp = await self.client.get(
            f'authorizations/token/{access_token}', token=token, headers=headers
        )
        return resp

    async def validate_token(self, token):
        # access_token = json.loads(token)["access_token"]
        token = json.loads(token)
        resp = await self._get_user_for_token(token)
        return resp.status_code == 200

    def configure(self, config: Config):

        self.is_enabled = JupyterConfigEntry.register(config)

        super().configure(config)
