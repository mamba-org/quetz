# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import enum

from sqlalchemy import (
    ARRAY,
    DDL,
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
    cast,
    event,
    func,
    sql,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import CompositeProperty, backref, composite, relationship
from sqlalchemy.schema import ForeignKeyConstraint
from sqlalchemy.types import TypeDecorator

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

    role = Column(String)

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

    name = Column(
        String(100, collation="nocase"),
        primary_key=True,
        index=True,
    )
    description = Column(String)
    private = Column(Boolean, default=False)
    mirror_channel_url = Column(String)
    mirror_mode = Column(String)
    timestamp_mirror_sync = Column(Integer, default=0)
    size = Column(Integer, default=0)
    size_limit = Column(Integer, default=None)

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
        "Package.channel_name == Channel.name)",
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


def version_numbers(version):
    return cast(func.string_to_array(version, '.'), ARRAY(Integer))


class VersionType(TypeDecorator):
    impl = String

    class comparator_factory(TypeDecorator.Comparator):
        def operate(self, op, other):
            return op(version_numbers(self.expr), version_numbers(other))


from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property


def parse_version(other):
    if isinstance(other, str):
        temp = other.split('.')
        temp = tuple(map(int, temp))
        return Version(*temp)
    elif isinstance(other, Version):
        return other
    else:
        raise Exception("unknown class")


class VersionComparator(CompositeProperty.Comparator):
    def __lt__(self, other):
        """redefine the 'greater than' operation"""
        v = self.__clause_element__().clauses
        other = parse_version(other)
        o = other.__composite_values__()

        return sql.or_(
            v[0] < o[0],
            sql.and_(v[0] == o[0], v[1] < o[1]),
            sql.and_(v[0] == o[0], v[1] == o[1], v[2] < v[2]),
        )

        # return sql.and_(*[a>b for a, b in
        #                  zip(self.__clause_element__().clauses,
        #                      other.__composite_values__())])


class Version:
    def __init__(self, major, minor=0, patch=0):
        self.major = major
        self.minor = minor
        self.patch = patch

    def __composite_values__(self):
        return self.major, self.minor, self.patch

    def __repr__(self):
        return f"{self.major}.{self.minor}.{self.patch}"

    def __eq__(self, other):
        return (
            isinstance(other, Version)
            and other.major == self.major
            and other.minor == self.minor
            and other.patch == self.patch
        )

    def __ne__(self, other):
        return not self.__eq__(other)


def default_ver(i):
    def _default(context):
        version = context.get_current_parameters()['version']
        try:
            return int(version.split('.')[i])
        except IndexError:
            return 0

    return _default


from sqlalchemy.event import listen
from sqlalchemy.orm import validates


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
    version = Column(VersionType)
    build_string = Column(String)
    build_number = Column(Integer)
    size = Column(Integer)

    version_order = Column(Integer, default=0)

    filename = Column(String)
    info = Column(String)
    uploader_id = Column(UUID, ForeignKey('users.id'))
    time_created = Column(DateTime(timezone=True), server_default=func.now())
    time_modified = Column(DateTime(timezone=True), server_default=func.now())
    package = relationship(
        "Package", backref=backref("package_versions", cascade="all,delete-orphan")
    )

    uploader = relationship('User')

    version_major = Column(Integer, default=default_ver(0))
    version_minor = Column(Integer, default=default_ver(1))
    version_patch = Column(Integer, default=default_ver(2))
    smart_version = composite(
        Version,
        version_major,
        version_minor,
        version_patch,
        comparator_factory=VersionComparator,
    )


def handler(target, value, old_value, initiator):
    return parse_version(value)


listen(PackageVersion.smart_version, 'set', handler, retval=True)

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
