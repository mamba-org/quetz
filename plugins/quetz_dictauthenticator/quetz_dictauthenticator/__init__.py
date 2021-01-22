from quetz.authentication.base import SimpleAuthenticator
from quetz.config import Config, ConfigEntry, ConfigSection


class DictionaryAuthenticator(SimpleAuthenticator):

    passwords: dict
    provider = "dict"

    def configure(self, config: Config):

        config.register(
            [
                ConfigSection(
                    "dictauthenticator",
                    [
                        ConfigEntry("users", list, default=list),
                    ],
                )
            ]
        )

        if config.configured_section("dictauthenticator"):
            self.passwords = dict(
                user_pass.split(":") for user_pass in config.dictauthenticator_users
            )
            self.is_enabled = True
        else:
            self.passwords = {}

    async def authenticate(self, request, data, **kwargs):
        if self.passwords.get(data['username']) == data['password']:
            return data['username']
