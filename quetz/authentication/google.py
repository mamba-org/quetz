# Copyright 2020 QuantStack, Codethink Ltd
# Distributed under the terms of the Modified BSD License.

from quetz.config import Config

from .oauth2 import OAuthAuthenticator


class GoogleAuthenticator(OAuthAuthenticator):
    """Use Google account to authenticate users with Quetz.

    To enable add the following to the configuration file:

    .. code::

      [google]
      client_id = "1111111111-dha39auqzp92110sdf.apps.googleusercontent.com"
      client_secret = "03728444a12abff17e9444fd231b4379d58f0b"

    You can obtain ``client_id`` and ``client_secret`` by registering your
    application with Google platfrom at this URL:
    `<https://console.developers.google.com/apis/credentials>`_.
    """

    provider = 'google'
    server_metadata_url = 'https://accounts.google.com/.well-known/openid-configuration'
    scope = "openid email profile"
    prompt = 'select_account'

    revoke_url = 'https://myaccount.google.com/permissions'
    validate_token_url = 'https://openidconnect.googleapis.com/v1/userinfo'

    collect_emails = False

    async def userinfo(self, request, token):
        profile = await self.client.parse_id_token(request, token)

        github_profile = {
            "id": profile["sub"],
            "name": profile["name"],
            "avatar_url": profile['picture'],
            "email": profile["email"],
            "login": profile["email"],
        }

        if self.collect_emails:
            github_profile["emails"] = [
                {
                    "email": profile["email"],
                    "primary": True,
                    "verified": profile["email_verified"],
                }
            ]

        return github_profile

    def configure(self, config: Config):
        if config.configured_section("google"):
            self.client_id = config.google_client_id
            self.client_secret = config.google_client_secret
            self.is_enabled = True
            if config.configured_section("users"):
                self.collect_emails = config.users_collect_emails

        else:
            self.is_enabled = False

        # call the configure of base class to set default_channel and default role
        super().configure(config)
