import hashlib

from sqlmodel import Field, SQLModel


class Credentials(SQLModel, table=True):  # type: ignore
    """Table for storing username and password, sha-256 hashed."""

    username: str = Field(primary_key=True)
    password: str


def calculate_hash(value: str) -> str:
    """Calculate hash from value."""
    return hashlib.sha256(value.encode()).hexdigest()
