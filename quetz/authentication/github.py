from pydantic import SecretStr

from quetz.authentication.oauth2 import OAuthAuthenticator
from quetz.config import PluginModel


class GithubAuthModel(PluginModel):
    client_id: str
    client_secret: SecretStr

    class Config:
        min_anystr_length = 1


class GithubAuthenticator(OAuthAuthenticator):
    """Use Github account to authenticate users with Quetz.

    To enable add the following to the configuration file:

    .. code::
      [auth]
      authenticators = ['github', ...]

      [github_authenticator]
      client_id = "fde330aef1fbe39991"
      client_secret = "03728444a12abff17e9444fd231b4379d58f0b"

    You can obtain ``client_id`` and ``client_secret`` by registering your
    application with Github at this URL:
    `<https://github.com/settings/applications/new>`_.
    """

    provider = "github"
    collect_emails = False

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

        if self.collect_emails:
            emails = await self.client.get('user/emails', token=token)
            profile["emails"] = emails.json()

        return profile

    @staticmethod
    def _make_config():
        return (GithubAuthModel, ...)

    def configure_plugin(self, config: GithubAuthModel):
        self.auto_configure(config)
