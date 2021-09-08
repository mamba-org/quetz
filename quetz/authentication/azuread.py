import json

from .oauth2 import OAuthAuthenticator


class AzureADAuthenticator(OAuthAuthenticator):
    """Use Microsoft Azure Active Directory account to authenticate users with Quetz.

    To enable add the following to the configuration file:

    .. code::

      [azuread]
      client_id = "some-client-id-value"
      client_secret = "a-client-secret"
      tenant_id = "tenant-name or id"

    You can obtain ``client_id`` and ``client_secret`` by registering your
    application with AzureAD platfrom at this URL:
    `https://portal.azure.com/#blade/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade/RegisteredApps`

    The ``tenant_id`` can either be a specific tenant's GUID identifier or one of three
    values:
    ``common``
    ``organizations``
    ``consumers``
    """

    provider = "azuread"
    collect_emails = False

    scope = "openid profile email"

    async def userinfo(self, request, token):
        response = await self.client.get(
            "https://graph.microsoft.com/oidc/userinfo", token=token
        )
        profile = response.json()

        azuread_profile = {
            "id": profile["sub"],
            "name": profile["name"],
            # TODO: the `picture` url requires to be requested with a bearer token.
            #  Thats not supported right now.
            # "avatar_url": profile["picture"],
            "avatar_url": "",
            "login": profile["email"],
        }

        if self.collect_emails:
            azuread_profile["emails"] = [
                {
                    "email": profile["email"],
                    "primary": True,
                    # AzureAD emails can always be considered to be verified.
                    # https://stackoverflow.com/questions/40618210/is-an-email-verified-in-azuread
                    "verified": True,
                }
            ]

        return azuread_profile

    async def authenticate(self, request, data=None, dao=None, config=None):
        token = await self.client.authorize_access_token(request)
        profile = await self.userinfo(request, token)

        username = profile["login"]

        # We have to remove the 'id_token' entry so we can save the token in a cookie
        # session
        token.pop('id_token', None)

        auth_state = {"token": json.dumps(token), "provider": self.provider}

        return {"username": username, "profile": profile, "auth_state": auth_state}

    def configure(self, config):
        if config.configured_section("azuread"):
            self.client_id = config.azuread_client_id
            self.client_secret = config.azuread_client_secret

            tenant_id = config.azuread_tenant_id
            self.server_metadata_url = (
                f'https://login.microsoftonline.com/{tenant_id}/v2.0/'
                f'.well-known/openid-configuration'
            )

            # oauth client params
            self.api_base_url = f'https://login.microsoftonline.com/{tenant_id}/v2.0'
            self.access_token_url = (
                f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'
            )
            self.authorize_url = (
                f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize'
            )
            # endpoints
            self.revoke_url = (
                f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout'
            )
            self.validate_token_url = 'https://graph.microsoft.com/oidc/userinfo'

            if config.configured_section("users"):
                self.collect_emails = config.users_collect_emails

            self.is_enabled = True
        else:
            self.is_enabled = False

        # call the configure of base class to set default_channel and default role
        super().configure(config)
