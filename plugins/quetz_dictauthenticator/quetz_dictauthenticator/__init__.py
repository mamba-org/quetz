from typing import Dict, Type, List

from quetz.authentication.base import (BaseAuthenticator, BaseAuthenticationHandlers, FormHandlers, UserProfile)
from quetz.config import PluginModel

class DictionaryAuthenticator(BaseAuthenticator):

    users: List[str]
    passwords: Dict[str, str]
    provider: str = "dict"
    handler_cls: Type[BaseAuthenticationHandlers] = FormHandlers

    class DictAuthConfig(PluginModel):
        users: List[str] = []

    @classmethod
    def _make_config(cls):
        return cls.DictAuthConfig()

    def configure_plugin(self, config: DictAuthConfig):
        self.auto_configure(config)

        self.passwords = dict(
            user_pass.split(":") for user_pass in self.users
        )

    async def authenticate(self, request, data, **kwargs):
        if self.passwords.get(data['username']) == data['password']:
            return data['username']
