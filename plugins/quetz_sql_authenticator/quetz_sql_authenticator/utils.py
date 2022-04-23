from sqlalchemy import Column, String

from quetz.db_models import Base


class Credentials(Base):
    __tablename__ = "credentials"

    username = Column("username", String, primary_key=True)
    password = Column("password", String)
