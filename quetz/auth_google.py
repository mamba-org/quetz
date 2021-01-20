# Copyright 2020 QuantStack, Codethink Ltd
# Distributed under the terms of the Modified BSD License.

from .auth_github import OAuthAuthenticator


class GoogleAuthenticator(OAuthAuthenticator):
    provider = 'google'
    server_metadata_url = 'https://accounts.google.com/.well-known/openid-configuration'
    scope = "openid email profile"
    prompt = 'select_account'

    revoke_url = 'https://myaccount.google.com/permissions'
    validate_token_url = 'https://openidconnect.googleapis.com/v1/userinfo'

    async def userinfo(self, request, token):
        profile = await self.client.parse_id_token(request, token)

        github_profile = {
            "id": profile["sub"],
            "name": profile["name"],
            "avatar_url": profile['picture'],
            "login": profile["email"],
        }
        return github_profile

    def configure(self, config):
        self.client_id = config.google_client_id
        self.client_secret = config.google_client_secret
        self.is_enabled = True
