from sqlmodel import Field, SQLModel


class Credentials(SQLModel, table=True):  # type: ignore
    """Table for storing username and password, sha-256 hashed."""

    username: str = Field(primary_key=True)
    password: str
