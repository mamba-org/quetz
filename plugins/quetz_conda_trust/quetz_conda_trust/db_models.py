import uuid

from sqlalchemy import Column, Date, ForeignKey, String, func

from quetz.db_models import UUID, Base


class RepodataSigningKey(Base):
    __tablename__ = 'repodata_signing_keys'

    id = Column(UUID, primary_key=True, default=lambda: uuid.uuid4().bytes)
    private_key = Column(String)
    time_created = Column(Date, nullable=False, server_default=func.now())
    user_id = Column(UUID, ForeignKey('users.id'))
    channel_name = Column(String, ForeignKey('channels.name'))
