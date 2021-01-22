import logging
from typing import Optional

import pamela
from fastapi import Request

from quetz.authentication.base import SimpleAuthenticator

logger = logging.getLogger("quetz")


class PAMAuthenticator(SimpleAuthenticator):

    provider: str = 'pam'

    service: str = "login"
    encoding: str = 'utf8'
    check_account: bool = True

    def configure(self, config):
        self.is_enabled = True

    async def authenticate(
        self,
        request: Request,
        data: Optional[dict] = None,
        dao=None,
        config=None,
        **kwargs
    ) -> Optional[str]:
        """Authenticate with PAM, and return the username if login is successful.
        Return None otherwise.
        """
        if data is None:
            return None

        username = data['username']
        try:
            pamela.authenticate(
                username, data['password'], service=self.service, encoding=self.encoding
            )
        except pamela.PAMError as e:
            logger.warning(
                "PAM Authentication failed (%s@%s): %s",
                username,
                request.client.host,
                e,
            )
            return None

        if self.check_account:
            try:
                pamela.check_account(
                    username, service=self.service, encoding=self.encoding
                )
            except pamela.PAMError as e:
                logger.warning(
                    "PAM Account Check failed (%s@%s): %s",
                    username,
                    request.client.host,
                    e,
                )
                return None

        return username
