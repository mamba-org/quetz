# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import enum
import json
import uuid

from sqlalchemy import (
    DDL,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    select,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, column_property, relationship
from sqlalchemy.schema import ForeignKeyConstraint

Base = declarative_base()

UUID = LargeBinary(length=16)


class User(Base):
    __tablename__ = 'users'

    id = Column(UUID, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)

    identities = relationship('Identity', back_populates='user', uselist=True)
    emails = relationship(
        'Email', back_populates='user', uselist=True, cascade="all,delete-orphan"
    )
    profile = relationship(
        'Profile', uselist=False, back_populates='user', cascade="all,delete-orphan"
    )

    role = Column(String)

    @classmethod
    def find(cls, db, name):
        """Find a user by name.
        Returns None if not found.
        """
        return db.query(cls).filter(cls.username == name).first()


class Email(Base):
    __tablename__ = "emails"

    __table_args__ = (
        ForeignKeyConstraint(
            ['provider', 'identity_id'],
            ['identities.provider', 'identities.identity_id'],
        ),
    )

    provider = Column(String, primary_key=True)
    identity_id = Column(String, primary_key=True)
    email = Column(String, primary_key=True, unique=True)

    user_id = Column(UUID, ForeignKey('users.id'))

    verified = Column(Boolean)
    primary = Column(Boolean)

    user = relationship('User', back_populates='emails')
    identity = relationship(
        'Identity', foreign_keys=[provider, identity_id], back_populates='emails'
    )


Index(
    'email_index',
    Email.provider,
    Email.identity_id,
    Email.email,
    unique=True,
)


class Identity(Base):
    __tablename__ = 'identities'

    provider = Column(String, primary_key=True)
    identity_id = Column(String, primary_key=True)
    username = Column(String)
    user_id = Column(UUID, ForeignKey('users.id'))

    user = relationship('User', back_populates='identities')
    emails = relationship('Email', back_populates='identity')


Index('identity_index', Identity.provider, Identity.identity_id, unique=True)


class Profile(Base):
    __tablename__ = 'profiles'

    name = Column(String, nullable=True)
    avatar_url = Column(String)
    user_id = Column(UUID, ForeignKey('users.id'), primary_key=True)
    user = relationship('User', back_populates='profile')


class ChannelMember(Base):
    __tablename__ = 'channel_members'

    channel_name = Column(
        String, ForeignKey('channels.name'), primary_key=True, index=True
    )
    user_id = Column(UUID, ForeignKey('users.id'), primary_key=True, index=True)
    role = Column(String)

    channel = relationship('Channel', back_populates="members")

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

    url = Column(String)

    platforms = Column(String)

    current_package_version = relationship(
        "PackageVersion",
        uselist=False,
        primaryjoin=(
            "and_(Package.name==PackageVersion.package_name, "
            "Package.channel_name==PackageVersion.channel_name, "
            "PackageVersion.version_order==0)"
        ),
        viewonly=True,
        lazy="select",
    )

    @property
    def current_version(self):
        return self.current_package_version.version

    @property
    def latest_change(self):
        return self.current_package_version.time_created

    def __repr__(self):
        return (
            f"<Package name={self.name}, summary={self.summary},"
            + f" channel={self.channel_name}>"
        )


class Channel(Base):
    __tablename__ = 'channels'

    name = Column(
        String(100, collation="nocase"),
        primary_key=True,
        index=True,
    )
    description = Column(String)
    private = Column(Boolean, default=False)
    mirror_channel_url = Column(String)
    mirror_mode = Column(String)
    channel_metadata = Column(String, server_default='{}', nullable=False)
    timestamp_mirror_sync = Column(Integer, default=0)
    size = Column(BigInteger, default=0)
    size_limit = Column(BigInteger, default=None)
    ttl = Column(Integer, server_default=f'{60 * 60 * 10}', nullable=False)  # 10 hours

    packages = relationship(
        'Package', back_populates='channel', cascade="all,delete", uselist=True
    )

    members = relationship('ChannelMember', cascade="all,delete")

    mirrors = relationship("ChannelMirror", cascade="all, delete", uselist=True)

    members_count = column_property(
        select([func.count(ChannelMember.user_id)])
        .where(ChannelMember.channel_name == name)
        .scalar_subquery(),  # type: ignore
        deferred=True,
    )

    def load_channel_metadata(self):
        if self.channel_metadata and len(self.channel_metadata) > 2:
            j = json.loads(self.channel_metadata)
            return j
        else:
            return {}

    packages_count = column_property(
        select([func.count(Package.name)])
        .where(Package.channel_name == name)
        .scalar_subquery(),  # type: ignore
        deferred=True,
    )

    def __repr__(self):
        return (
            f"<Channel name={self.name}, "
            "description={self.description}, "
            "private={self.private}>"
        )


class PackageMember(Base):
    __tablename__ = 'package_members'
    __table_args__ = (
        ForeignKeyConstraint(
            ["channel_name", "package_name"], ["packages.channel_name", "packages.name"]
        ),
        ForeignKeyConstraint(["channel_name"], ["channels.name"]),
        ForeignKeyConstraint(["user_id"], ["users.id"]),
    )

    channel_name = Column(String, primary_key=True, index=True)
    package_name = Column(String, primary_key=True, index=True)
    user_id = Column(UUID, primary_key=True, index=True)
    role = Column(String)

    # primaryjoin condition is needed to avoid conflicts between channel and package
    # relationships that share the same foreign key (channel_name): for package
    # channel_name is only required to lookup the package using the composite key
    # (channel_name + package_name) whereas for channel relationship the channel_name
    # is a writeable column

    # see also : https://docs.sqlalchemy.org/en/13/orm/join_conditions.html#overlapping-foreign-keys # noqa

    package = relationship(
        'Package',
        backref=backref("members", cascade="all,delete"),
        primaryjoin="and_(Package.name == foreign(PackageMember.package_name),"
        "Package.channel_name == PackageMember.channel_name)",
    )
    channel = relationship(
        'Channel', backref=backref("package_members", cascade="all,delete")
    )
    user = relationship('User', backref=backref("packages", cascade="all,delete"))

    def __repr__(self):
        return f'<PackageMember channel_name={self.channel_name}, package_name={self.package_name},\
        role={self.role}>'


class ApiKey(Base):
    __tablename__ = 'api_keys'

    key = Column(String, primary_key=True, index=True)
    description = Column(String)
    time_created = Column(Date, nullable=False, server_default=func.now())
    expire_at = Column(Date)
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
    size = Column(BigInteger)

    version_order = Column(Integer, default=0)

    download_count = Column(Integer, default=0)

    filename = Column(String)
    info = Column(String)
    uploader_id = Column(UUID, ForeignKey('users.id'))
    time_created = Column(DateTime(timezone=True), server_default=func.now())
    time_modified = Column(DateTime(timezone=True), server_default=func.now())
    package = relationship(
        "Package", backref=backref("package_versions", cascade="all,delete-orphan")
    )

    uploader = relationship('User')


class ChannelMirror(Base):
    __tablename__ = "channel_mirrors"

    id = Column(UUID, primary_key=True, default=lambda: uuid.uuid4().bytes)
    channel_name = Column(String, ForeignKey("channels.name"))
    url = Column(String, nullable=False, unique=True)
    api_endpoint = Column(String, nullable=True)
    metrics_endpoint = Column(String, nullable=True)
    last_synchronised = Column(DateTime, default=None)


Index(
    'package_version_name_index',
    PackageVersion.channel_name,
    PackageVersion.package_name,
)

Index(
    'package_version_filename_index',
    PackageVersion.channel_name,
    PackageVersion.filename,
    PackageVersion.platform,
    unique=True,
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


collation = DDL(
    "CREATE COLLATION IF NOT EXISTS nocase ("
    "provider = icu, "
    "locale = 'und-u-ks-level2', "
    "deterministic = false);"
)

event.listen(
    Channel.__table__,
    'before_create',
    collation.execute_if(dialect='postgresql'),  # type: ignore
)
