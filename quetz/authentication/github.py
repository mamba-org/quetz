from .oauth2 import OAuthAuthenticator


class GithubAuthenticator(OAuthAuthenticator):
    # Register the app here: https://github.com/settings/applications/new

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
        if config.configured_section("github"):
            self.client_id = config.github_client_id
            self.client_secret = config.github_client_secret
            self.is_enabled = True
        else:
            self.is_enabled = False

        # call the configure of base class to set default_channel and default role
        super().configure(config)
