from passlib.hash import pbkdf2_sha256

import quetz
from quetz.authentication.base import SimpleAuthenticator
from quetz.database import get_db_manager

from .api import router
from .db_models import Credentials


def _verify_hash(value: str, hash: str) -> bool:
    """Verify value against hash."""
    return pbkdf2_sha256.verify(value, hash)


@quetz.hookimpl
def register_router():
    return router


class UsernameNotFound(RuntimeError):
    """Error that is thrown when the username is not found."""


def _get_password_hash(username: str) -> str:
    with get_db_manager() as db:
        credentials = (
            db.query(Credentials).filter(Credentials.username == username).one_or_none()
        )
        if credentials is None:
            raise UsernameNotFound(f"Username '{username}' not found.")
        return credentials.password_hash


class SQLAuthenticator(SimpleAuthenticator):
    """An authenticator that uses a SQLAlchemy backend."""

    provider = "sql"

    async def authenticate(self, request, data, **kwargs):
        """Authenticate."""
        try:
            password_hash = _get_password_hash(data["username"])
        except UsernameNotFound:
            return
        if _verify_hash(data["password"], password_hash):
            return data["username"]
