# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from sqlalchemy.orm import Session, joinedload, aliased, Query
from .db_models import (
    Profile,
    User,
    Channel,
    ChannelMember,
    Package,
    PackageMember,
    ApiKey,
    PackageVersion,
)
from quetz import rest_models, channel_data
import uuid
import json


def get_paginated_result(query: Query, skip: int, limit: int):
    return {
        'pagination': {
            'skip': skip,
            'limit': limit,
            'all_records_count': query.order_by(None).count(),
        },
        'result': query.offset(skip).limit(limit).all(),
    }


class Dao:
    def __init__(self, db: Session):
        self.db = db

    def rollback(self):
        self.db.rollback()

    def get_profile(self, user_id):
        return self.db.query(Profile).filter(Profile.user_id == user_id).one()

    def get_user(self, user_id):
        return self.db.query(User).filter(User.id == user_id).one()

    def get_users(self, skip: int, limit: int, q: str):
        query = self.db.query(User).filter(User.username.isnot(None))

        if q:
            query = query.filter(User.username.ilike(f'%{q}%'))

        query = query.options(joinedload(User.profile))

        if limit < 0:
            return query.all()

        return get_paginated_result(query, skip, limit)

    def get_user_by_username(self, username: str):
        return (
            self.db.query(User)
            .filter(User.username == username)
            .options(joinedload(User.profile))
            .one_or_none()
        )

    def get_channels(self, skip: int, limit: int, q: str):
        query = self.db.query(Channel)

        if q:
            query = query.filter(Channel.name.ilike(f'%{q}%'))

        if limit < 0:
            return query.all()

        return get_paginated_result(query, skip, limit)

    def create_channel(self, data: rest_models.Channel, user_id: bytes, role: str):
        channel = Channel(name=data.name, description=data.description)

        member = ChannelMember(channel=channel, user_id=user_id, role=role)

        self.db.add(channel)
        self.db.add(member)
        self.db.commit()

    def get_packages(self, channel_name: str, skip: int, limit: int, q: str):
        query = self.db.query(Package).filter(Package.channel_name == channel_name)

        if q:
            query = query.filter(Package.name.like(f'%{q}%'))

        if limit < 0:
            return query.all()

        return get_paginated_result(query, skip, limit)

    def get_channel(self, channel_name: str):
        return self.db.query(Channel).filter(Channel.name == channel_name).one_or_none()

    def get_package(self, channel_name: str, package_name: str):
        return (
            self.db.query(Package)
            .join(Channel)
            .filter(Channel.name == channel_name)
            .filter(Package.name == package_name)
            .one_or_none()
        )

    def create_package(
        self,
        channel_name: str,
        new_package: rest_models.Package,
        user_id: bytes,
        role: str,
    ):
        package = Package(
            name=new_package.name,
            summary=new_package.summary,
            description=new_package.description,
            channeldata="{}",
        )

        package.channel = (
            self.db.query(Channel).filter(Channel.name == channel_name).one()
        )

        member = PackageMember(
            channel=package.channel, package=package, user_id=user_id, role=role
        )

        self.db.add(package)
        self.db.add(member)
        self.db.commit()

    def update_package_channeldata(self, channel_name, package_name, channeldata):
        package = self.get_package(channel_name, package_name)
        if package.channeldata:
            old_data = json.loads(package.channeldata)
        else:
            old_data = None
        data = channel_data.combine(old_data, channeldata)
        package.channeldata = json.dumps(data)
        self.db.commit()

    def get_channel_members(self, channel_name: str):
        return (
            self.db.query(ChannelMember)
            .join(User)
            .filter(ChannelMember.channel_name == channel_name)
            .all()
        )

    def get_channel_member(self, channel_name, username):
        return (
            self.db.query(ChannelMember)
            .join(User)
            .filter(ChannelMember.channel_name == channel_name)
            .filter(User.username == username)
            .one_or_none()
        )

    def create_channel_member(self, channel_name, new_member):
        user = self.get_user_by_username(new_member.username)

        member = ChannelMember(
            channel_name=channel_name, user_id=user.id, role=new_member.role
        )

        self.db.add(member)
        self.db.commit()

    def get_package_members(self, channel_name, package_name):
        return (
            self.db.query(PackageMember)
            .join(User)
            .filter(User.username.isnot(None))
            .filter(PackageMember.channel_name == channel_name)
            .filter(PackageMember.package_name == package_name)
            .all()
        )

    def get_package_member(self, channel_name, package_name, username):
        return (
            self.db.query(PackageMember)
            .join(User)
            .filter(PackageMember.channel_name == channel_name)
            .filter(PackageMember.package_name == package_name)
            .filter(User.username == username)
            .one_or_none()
        )

    def create_package_member(self, channel_name, package_name, new_member):
        user = self.get_user_by_username(new_member.username)

        member = PackageMember(
            channel_name=channel_name,
            package_name=package_name,
            user_id=user.id,
            role=new_member.role,
        )

        self.db.add(member)
        self.db.commit()

    def get_package_api_keys(self, user_id):
        return (
            self.db.query(PackageMember, ApiKey)
            .join(User, PackageMember.user_id == User.id)
            .join(ApiKey, ApiKey.user_id == User.id)
            .filter(ApiKey.owner_id == user_id)
            .all()
        )

    def get_channel_api_keys(self, user_id):
        return (
            self.db.query(ChannelMember, ApiKey)
            .join(User, ChannelMember.user_id == User.id)
            .join(ApiKey, ApiKey.user_id == User.id)
            .filter(ApiKey.owner_id == user_id)
            .all()
        )

    def create_api_key(self, user_id, api_key: rest_models.BaseApiKey, key):
        user = User(id=uuid.uuid4().bytes)
        owner = self.get_user(user_id)
        db_api_key = ApiKey(
            key=key, description=api_key.description, user=user, owner=owner
        )

        self.db.add(db_api_key)
        for role in api_key.roles:
            if role.package:
                package_member = PackageMember(
                    user=user,
                    channel_name=role.channel,
                    package_name=role.package,
                    role=role.role,
                )
                self.db.add(package_member)
            else:
                channel_member = ChannelMember(
                    user=user, channel_name=role.channel, role=role.role
                )
                self.db.add(channel_member)

        self.db.commit()

    def create_version(
        self,
        channel_name,
        package_name,
        package_format,
        platform,
        version,
        build_number,
        build_string,
        filename,
        info,
        uploader_id,
    ):
        version = PackageVersion(
            id=uuid.uuid4().bytes,
            channel_name=channel_name,
            package_name=package_name,
            package_format=package_format,
            platform=platform,
            version=version,
            build_number=build_number,
            build_string=build_string,
            filename=filename,
            info=info,
            uploader_id=uploader_id,
        )
        self.db.add(version)
        self.db.commit()

    def get_package_versions(self, package):
        ApiKeyProfile = aliased(Profile)

        return (
            self.db.query(PackageVersion, Profile, ApiKeyProfile)
            .outerjoin(Profile, Profile.user_id == PackageVersion.uploader_id)
            .outerjoin(ApiKey, ApiKey.user_id == PackageVersion.uploader_id)
            .outerjoin(ApiKeyProfile, ApiKey.owner_id == ApiKeyProfile.user_id)
            .filter(PackageVersion.channel_name == package.channel_name)
            .filter(PackageVersion.package_name == package.name)
            .all()
        )

    def is_active_platform(self, channel_name: str, platform: str):
        return (
            self.db.query(PackageVersion)
            .filter(PackageVersion.channel_name == channel_name)
            .filter(PackageVersion.platform == platform)
            .count()
            > 0
        )

    def get_package_infos(self, channel_name: str, subdir: str):
        # Returns iterator
        return (
            self.db.query(
                PackageVersion.filename,
                PackageVersion.info,
                PackageVersion.package_format,
            )
            .filter(PackageVersion.channel_name == channel_name)
            .filter(PackageVersion.platform.in_([subdir, "noarch"]))
            .order_by(PackageVersion.filename)
        )

    def get_channel_datas(self, channel_name: str):
        # Returns iterator
        return (
            self.db.query(Package.name, Package.channeldata)
            .filter(Package.channel_name == channel_name)
            .order_by(Package.name)
        )
