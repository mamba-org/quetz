import logging
from typing import Dict

from . import BaseAuthenticator

logger = logging.getLogger("quetz")


class AuthenticatorRegistry:

    _instance = None
    _router = None
    enabled_authenticators: Dict[str, BaseAuthenticator] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def set_router(cls, router):
        cls._router = router

    def register(self, auth: BaseAuthenticator):
        if auth.provider in self.enabled_authenticators:
            logger.warning(f"authenticator '{auth.provider}' already registered")
            return

        if not self._router:
            raise Exception(
                "AuthenticationRegistry not completely configure, you need to set the"
                "root router using set_router method"
            )
        self._router.include_router(auth.router)
        self.enabled_authenticators[auth.provider] = auth
        logger.info(
            f"authentication provider '{auth.provider}' "
            f"of class {auth.__class__.__name__} registered"
        )

        if len(self.enabled_authenticators) > 1:
            logger.warning(
                "You have registered multiple authentication providers."
                "Please note that this is currently discouraged in production setups!"
            )

    def is_registered(self, provider_name: str):
        return provider_name in self.enabled_authenticators
