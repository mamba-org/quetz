from sqlalchemy import Column, ForeignKey, String, BLOB, Index, Boolean
from sqlalchemy.orm import relationship

from .database import Base

UUID = BLOB(length=16)


class User(Base):
    __tablename__ = 'users'

    id = Column(UUID, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)

    identities = relationship('Identity', back_populates='user')
    profile = relationship('Profile', uselist=False, back_populates='user')


class Identity(Base):
    __tablename__ = 'identities'

    provider = Column(String, primary_key=True)
    identity_id = Column(String, primary_key=True)
    username = Column(String)
    user_id = Column(UUID, ForeignKey('users.id'))

    user = relationship('User', back_populates='identities')


Index('identity_index', Identity.provider, Identity.identity_id, unique=True)


class Profile(Base):
    __tablename__ = 'profiles'

    name = Column(String)
    avatar_url = Column(String)
    user_id = Column(UUID, ForeignKey('users.id'), primary_key=True)
    user = relationship('User', back_populates='profile')


class Channel(Base):
    __tablename__ = 'channels'

    name = Column(String, primary_key=True, index=True)
    description = Column(String)
    private = Column(Boolean, default=False)

    packages = relationship('Package', back_populates='channel')

    def __repr__(self):
        return f'<Channel name={self.name}, description={self.description}, private={self.private}>'


class ChannelMember(Base):
    __tablename__ = 'channel_members'

    channel_name = Column(String, ForeignKey('channels.name'), primary_key=True, index=True)
    user_id = Column(UUID, ForeignKey('users.id'), primary_key=True, index=True)
    role = Column(String)

    channel = relationship('Channel')
    user = relationship('User')


class Package(Base):
    __tablename__ = 'packages'

    name = Column(String, primary_key=True, index=True)
    channel_name = Column(String, ForeignKey('channels.name'), primary_key=True, index=True)
    description = Column(String)

    channel = relationship('Channel', uselist=False, back_populates='packages')

    def __repr__(self):
        return f'<Package name={self.name}, description={self.description}, channel={self.channel}>'


class PackageMember(Base):
    __tablename__ = 'package_members'

    channel_name = Column(String, ForeignKey('channels.name'), primary_key=True, index=True)
    package_name = Column(String, ForeignKey('packages.name'), primary_key=True, index=True)
    user_id = Column(UUID, ForeignKey('users.id'), primary_key=True, index=True)
    role = Column(String)

    package = relationship('Package')
    channel = relationship('Channel')
    user = relationship('User')

    def __repr__(self):
        return f'<PackageMember channel_name={self.channel_name}, package_name={self.package_name},\
        role={self.role}>'


class ApiKey(Base):
    __tablename__ = 'api_keys'

    key = Column(String, primary_key=True, index=True)
    description = Column(String)
    deleted = Column(Boolean, default=False)
    user_id = Column(UUID, ForeignKey('users.id'))
    owner_id = Column(UUID, ForeignKey('users.id'))

    user = relationship('User', foreign_keys=[user_id])
    owner = relationship('User', foreign_keys=[owner_id])

    def __repr__(self):
        return f'<ApiKey key={self.key}>'
