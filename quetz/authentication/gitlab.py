from .oauth2 import OAuthAuthenticator


class GitlabAuthenticator(OAuthAuthenticator):
    """Use Gitlab account to authenticate users with Quetz.

    To enable add the following to the configuration file:

    .. code::

      [gitlab]
      client_id = "fde330aef1fbe39991"
      client_secret = "03728444a12abff17e9444fd231b4379d58f0b"

    The above will use `<https://gitlab.com>`_. You can specify a self-hosted
    GitLab instance using the ``url`` parameter:

    .. code::

      [gitlab]
      url = "https://gitlab.mydomain.org"
      client_id = "fde330aef1fbe39991"
      client_secret = "03728444a12abff17e9444fd231b4379d58f0b"

    You can obtain ``client_id`` and ``client_secret`` by registering your
    application with Gitlab at this URL:
    `<https://gitlab.com/-/profile/applications>`_ or
    `<https://gitlab.mydomain.org/admin/applications>`_
    if using a self-hosted GitLab instance.
    Select ``openid`` as scope. If you want to collect email addresses,
    make sure to also select ``email``, ``profile`` and ``read_user`` as scope
    in the Gitlab interface.
    """

    provider = "gitlab"

    collect_emails = False

    # oauth client params
    scope = 'openid'

    # endpoint urls
    validate_token_url = "user"

    async def userinfo(self, request, token):
        resp = await self.client.get('/oauth/userinfo', token=token)
        profile = resp.json()
        gitlab_profile = {
            "id": profile["sub"],
            "name": profile["name"],
            "avatar_url": profile["picture"],
            "login": profile["nickname"],
        }

        # https://docs.gitlab.com/ee/integration/openid_connect_provider.html#shared-information
        if self.collect_emails:
            emails = await self.client.get('/api/v4/user/emails', token=token)
            emails_res = []
            emails_res.append(
                {
                    "email": profile["email"],
                    "primary": True,
                    "verified": profile["email_verified"],
                }
            )

            for e in emails.json():
                # there is a bug in gitlab so this should never be true (currently)
                if e["email"] == profile["email"]:
                    continue

                x = {
                    "email": e["email"],
                    "primary": False,
                    "verified": e["confirmed_at"] is not None,
                }
                emails_res.append(x)

            gitlab_profile["emails"] = emails_res

        return gitlab_profile

    def configure(self, config):
        if config.configured_section("gitlab"):
            self.access_token_url = f'{config.gitlab_url}/oauth/token'
            self.authorize_url = f'{config.gitlab_url}/oauth/authorize'
            self.api_base_url = f'{config.gitlab_url}/api/v4'
            self.revoke_url = f'{config.gitlab_url}/oauth/applications'
            self.client_id = config.gitlab_client_id
            self.client_secret = config.gitlab_client_secret
            self.is_enabled = True
            if config.configured_section("users"):
                self.collect_emails = config.users_collect_emails
                self.scope = 'openid email read_user'

        else:
            self.is_enabled = False

        # call the configure of base class to set default_channel and default role
        super().configure(config)
