from quetz.authentication.base import SimpleAuthenticator


class DictionaryAuthenticator(SimpleAuthenticator):

    passwords: dict
    provider = "dict"

    def configure(self, config):
        self.passwords = {"happyuser": "happy"}

    async def authenticate(self, request, data, **kwargs):
        if self.passwords.get(data['username']) == data['password']:
            return data['username']
