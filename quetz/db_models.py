# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, relationship
from sqlalchemy.schema import ForeignKeyConstraint

Base = declarative_base()

UUID = LargeBinary(length=16)


class User(Base):
    __tablename__ = 'users'

    id = Column(UUID, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)

    identities = relationship('Identity', back_populates='user')
    profile = relationship(
        'Profile', uselist=False, back_populates='user', cascade="all,delete-orphan"
    )

    @classmethod
    def find(cls, db, name):
        """Find a user by name.
        Returns None if not found.
        """
        return db.query(cls).filter(cls.username == name).first()


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

    name = Column(String, nullable=True)
    avatar_url = Column(String)
    user_id = Column(UUID, ForeignKey('users.id'), primary_key=True)
    user = relationship('User', back_populates='profile')


class Channel(Base):
    __tablename__ = 'channels'

    name = Column(String, primary_key=True, index=True)
    description = Column(String)
    private = Column(Boolean, default=False)
    mirror_channel_url = Column(String)
    mirror_mode = Column(String, default="proxy")
    timestamp_mirror_sync = Column(Integer, default=0)

    packages = relationship('Package', back_populates='channel', cascade="all,delete")

    members = relationship('ChannelMember', cascade="all,delete")

    def __repr__(self):
        return (
            f"<Channel name={self.name}, "
            "description={self.description}, "
            "private={self.private}>"
        )


class ChannelMember(Base):
    __tablename__ = 'channel_members'

    channel_name = Column(
        String, ForeignKey('channels.name'), primary_key=True, index=True
    )
    user_id = Column(UUID, ForeignKey('users.id'), primary_key=True, index=True)
    role = Column(String)

    channel = relationship(
        'Channel', backref=backref("channel_members", cascade="all,delete-orphan")
    )
    user = relationship(
        'User', backref=backref("channel_members", cascade="all,delete-orphan")
    )

    def __repr__(self):
        return (
            f'ChannelMember<{self.user.username} -> {self.channel_name} ({self.role})>'
        )


class Package(Base):
    __tablename__ = 'packages'

    name = Column(String, primary_key=True, index=True)
    channel_name = Column(
        String, ForeignKey('channels.name'), primary_key=True, index=True
    )
    description = Column(Text)
    summary = Column(Text)

    channel = relationship('Channel', uselist=False, back_populates='packages')

    # channeldata is always from the most recent version
    channeldata = Column(String)

    def __repr__(self):
        return (
            f"<Package name={self.name}, summary={self.summary},"
            + f" channel={self.channel_name}>"
        )


class PackageMember(Base):
    __tablename__ = 'package_members'
    __table_args__ = (
        ForeignKeyConstraint(
            ["channel_name", "package_name"], ["packages.channel_name", "packages.name"]
        ),
        ForeignKeyConstraint(["channel_name"], ["channels.name"]),
    )

    channel_name = Column(String, primary_key=True, index=True)
    package_name = Column(String, primary_key=True, index=True)
    user_id = Column(UUID, ForeignKey('users.id'), primary_key=True, index=True)
    role = Column(String)

    # primaryjoin condition is needed to avoid conflicts between channel and package
    # relationships

    # see: https://docs.sqlalchemy.org/en/13/orm/join_conditions.html#overlapping-foreign-keys # noqa
    package = relationship(
        'Package',
        backref=backref("members", cascade="all,delete"),
        primaryjoin="and_(Package.name == foreign(PackageMember.package_name),"
        "Package.channel_name == Channel.name)",
        # foreign_keys="PackageMember.package_name",
    )
    channel = relationship('Channel')
    user = relationship('User', backref=backref("packages", cascade="all,delete"))

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

    user = relationship(
        'User',
        foreign_keys=[user_id],
        backref=backref("api_keys_user", cascade="all,delete-orphan"),
    )
    owner = relationship(
        'User',
        foreign_keys=[owner_id],
        backref=backref("api_keys_owner", cascade="all,delete-orphan"),
    )

    def __repr__(self):
        return f'<ApiKey key={self.key}>'


class PackageFormatEnum(enum.Enum):
    tarbz2 = 1
    conda = 2


class PackageVersion(Base):
    __tablename__ = 'package_versions'
    __table_args__ = (
        ForeignKeyConstraint(
            ["channel_name", "package_name"], ["packages.channel_name", "packages.name"]
        ),
        ForeignKeyConstraint(["channel_name"], ["channels.name"]),
    )

    id = Column(UUID, primary_key=True)
    channel_name = Column(String)
    package_name = Column(String)
    package_format = Column(Enum(PackageFormatEnum))
    platform = Column(String)
    version = Column(String)
    build_string = Column(String)
    build_number = Column(Integer)

    filename = Column(String)
    info = Column(String)
    uploader_id = Column(UUID, ForeignKey('users.id'))
    time_created = Column(DateTime(timezone=True), server_default=func.now())
    time_modified = Column(DateTime(timezone=True), server_default=func.now())
    package = relationship(
        "Package", backref=backref("package_versions", cascade="all,delete-orphan")
    )

    uploader = relationship('User')


Index(
    'package_version_name_index',
    PackageVersion.channel_name,
    PackageVersion.package_name,
)

UniqueConstraint(
    PackageVersion.channel_name,
    PackageVersion.package_name,
    PackageVersion.package_format,
    PackageVersion.platform,
    PackageVersion.version,
    PackageVersion.build_string,
    PackageVersion.build_number,
    name='package_version_index',
)
