import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, func

from quetz.db_models import UUID, Base


class TermsOfService(Base):
    __tablename__ = 'quetz_tos'

    id = Column(UUID, primary_key=True, default=lambda: uuid.uuid4().bytes)
    uploader_id = Column(UUID)
    filename = Column(String)
    time_created = Column(DateTime, nullable=False, server_default=func.now())


class TermsOfServiceSignatures(Base):
    __tablename__ = "quetz_tos_signatures"
    __table_args__ = (UniqueConstraint('tos_id', 'user_id'),)

    tos_id = Column(UUID, ForeignKey('quetz_tos.id'), primary_key=True)
    user_id = Column(UUID, ForeignKey('users.id'), primary_key=True)
    time_created = Column(DateTime, nullable=False, server_default=func.now())
