from passlib.hash import pbkdf2_sha256
from sqlmodel import Session, create_engine, select

from quetz.authentication.base import SimpleAuthenticator
from quetz.config import Config, ConfigEntry, ConfigSection

from .utils import Credentials


class UsernameNotFound(RuntimeError):
    """Error that is thrown when the username is not found."""


def _get_password_hashed(username: str, session: Session) -> str:
    result = session.exec(
        select(Credentials).where(Credentials.username == username)
    ).first()
    if result:
        return result.password
    raise UsernameNotFound(username)


_CONFIG_NAME = "sql_authenticator"

_CONFIG = [
    ConfigSection(
        _CONFIG_NAME,
        [
            ConfigEntry(
                name="database_url",
                cast=str,
                required=True,
            )
        ],
    )
]


class SQLAuthenticator(SimpleAuthenticator):
    """An authenticator that uses a SQLAlchemy backend."""

    provider = "sql"

    def configure(self, config: Config):
        """Configure."""
        config.register(_CONFIG)

        if config.configured_section(_CONFIG_NAME):
            self._engine = create_engine(
                getattr(config, f"{_CONFIG_NAME}_database_url")
            )
            self.is_enabled = True

        super().configure(config)

    async def authenticate(self, request, data, **kwargs):
        """Authenticate."""
        with Session(self._engine) as session:
            try:
                password_hashed = _get_password_hashed(data["username"], session)
            except UsernameNotFound:
                return
        if pbkdf2_sha256.verify(data["password"], password_hashed):
            return data["username"]
