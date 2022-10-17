from passlib.hash import pbkdf2_sha256

from quetz.authentication.base import SimpleAuthenticator
from quetz.database import get_db_manager

from .db_models import Credentials


class UsernameNotFound(RuntimeError):
    """Error that is thrown when the username is not found."""


def _get_password_hashed(username: str) -> str:
    with get_db_manager() as db:
        credentials = (
            db.query(Credentials).filter(Credentials.username == username).one_or_none()
        )
        if credentials is None:
            raise UsernameNotFound(f"Username '{username}' not found.")
        return credentials.password


class SQLAuthenticator(SimpleAuthenticator):
    """An authenticator that uses a SQLAlchemy backend."""

    provider = "sql"

    async def authenticate(self, request, data, **kwargs):
        """Authenticate."""
        try:
            password_hashed = _get_password_hashed(data["username"])
        except UsernameNotFound:
            return
        if pbkdf2_sha256.verify(data["password"], password_hashed):
            return data["username"]
