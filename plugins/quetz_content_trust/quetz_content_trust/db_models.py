import uuid

from sqlalchemy import BigInteger, Column, Date, ForeignKey, String, Table, func
from sqlalchemy.orm import relationship

from quetz.db_models import UUID, Base

association_table = Table(
    "delegations_keys",
    Base.metadata,
    Column("role_delegations_id", ForeignKey("role_delegations.id"), primary_key=True),
    Column(
        "signing_keys_public_key",
        ForeignKey("signing_keys.public_key"),
        primary_key=True,
    ),
)


class ContentTrustRole(Base):
    __tablename__ = "content_trust_roles"

    id = Column(
        UUID, primary_key=False, unique=True, default=lambda: uuid.uuid4().bytes
    )
    type = Column(String, nullable=False, primary_key=True)
    channel = Column(String, nullable=False, primary_key=True)
    version = Column(BigInteger, nullable=False, primary_key=True)

    timestamp = Column(String, nullable=False)
    expiration = Column(String, nullable=False)

    delegator_id = Column(UUID, ForeignKey("role_delegations.id"), nullable=True)
    delegations = relationship(
        "RoleDelegation",
        backref="issuer",
        foreign_keys="RoleDelegation.issuer_id",
        cascade="all, delete-orphan",
    )

    # delegator created by 'role_delegations.consumers' relationship backref

    time_created = Column(Date, nullable=False, server_default=func.current_date())


class RoleDelegation(Base):
    __tablename__ = "role_delegations"

    id = Column(UUID, primary_key=True, default=lambda: uuid.uuid4().bytes)

    issuer_id = Column(UUID, ForeignKey("content_trust_roles.id"), nullable=False)
    consumers = relationship(
        "ContentTrustRole",
        backref="delegator",
        foreign_keys=ContentTrustRole.delegator_id,
        post_update=True,
        cascade="all, delete-orphan",
    )

    # issuer created by 'content_trust_roles.delegations' relationship backref

    type = Column(String, nullable=False)
    channel = Column(String, nullable=False)
    threshold = Column(BigInteger, nullable=False)
    keys = relationship(
        "SigningKey", secondary=association_table, backref="delegations"
    )
    time_created = Column(Date, nullable=False, server_default=func.current_date())


class SigningKey(Base):
    __tablename__ = "signing_keys"

    public_key = Column(String, primary_key=True)
    private_key = Column(String)
    time_created = Column(Date, nullable=False, server_default=func.current_date())
    user_id = Column(UUID, ForeignKey("users.id"))
    channel_name = Column(String, ForeignKey("channels.name"))
