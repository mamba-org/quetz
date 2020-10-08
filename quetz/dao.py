# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session, aliased, joinedload

from quetz import channel_data, rest_models

from .db_models import (
    ApiKey,
    Channel,
    ChannelMember,
    Package,
    PackageMember,
    PackageVersion,
    Profile,
    User,
)


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

    def get_channels(
        self, skip: int, limit: int, q: Optional[str], user_id: Optional[bytes]
    ):
        query = self.db.query(Channel)

        if user_id:
            query = query.filter(
                or_(
                    Channel.private == False,  # noqa
                    Channel.members.any(ChannelMember.user_id == user_id),
                )
            )
        else:
            query = query.filter(Channel.private == False)  # noqa

        if q:
            query = query.filter(Channel.name.ilike(f'%{q}%'))

        if limit < 0:
            return query.all()

        return get_paginated_result(query, skip, limit)

    def create_channel(self, data: rest_models.Channel, user_id: bytes, role: str):
        channel = Channel(
            name=data.name,
            description=data.description,
            mirror_channel_url=data.mirror_channel_url,
            mirror_mode=data.mirror_mode,
            private=data.private,
        )

        member = ChannelMember(channel=channel, user_id=user_id, role=role)

        self.db.add(channel)
        self.db.add(member)
        self.db.commit()

        return channel

    def update_channel(self, channel_name, data: dict):

        self.db.query(Channel).filter(Channel.name == channel_name).update(
            data, synchronize_session=False
        )
        self.db.commit()

    def get_packages(self, channel_name: str, skip: int, limit: int, q: str):
        query = self.db.query(Package).filter(Package.channel_name == channel_name)

        if q:
            query = query.filter(Package.name.like(f'%{q}%'))

        if limit < 0:
            return query.all()

        return get_paginated_result(query, skip, limit)

    def search_packages(self, q: str, user_id: Optional[bytes]):
        query = (
            self.db.query(Package).join(Channel).filter(Package.name.ilike(f'%{q}%'))
        )
        if user_id:
            query = query.filter(
                or_(
                    Channel.private == False,  # noqa
                    Channel.members.any(ChannelMember.user_id == user_id),
                )
            )
        else:
            query = query.filter(Channel.private == False)  # noqa

        return query.all()

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

        return package

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

        return db_api_key

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
        upsert: bool = False,
    ):

        existing_versions = (
            self.db.query(PackageVersion)
            .filter(PackageVersion.channel_name == channel_name)
            .filter(PackageVersion.package_name == package_name)
            .filter(PackageVersion.package_format == package_format)
            .filter(PackageVersion.platform == platform)
            .filter(PackageVersion.version == version)
            .filter(PackageVersion.build_number == build_number)
            .filter(PackageVersion.build_string == build_string)
        )
        package_version = existing_versions.one_or_none()
        if not package_version:
            package_version = PackageVersion(
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
            self.db.add(package_version)
        elif upsert:
            existing_versions.update(
                {
                    "filename": filename,
                    "info": info,
                    "uploader_id": uploader_id,
                    "time_modified": datetime.utcnow(),
                },
                synchronize_session=False,
            )
        else:
            raise IntegrityError("duplicate package version", "", "")

        self.db.commit()

        return package_version

    def get_package_versions(self, package, time_created_ge: datetime = None):
        ApiKeyProfile = aliased(Profile)

        query = (
            self.db.query(PackageVersion, Profile, ApiKeyProfile)
            .outerjoin(Profile, Profile.user_id == PackageVersion.uploader_id)
            .outerjoin(ApiKey, ApiKey.user_id == PackageVersion.uploader_id)
            .outerjoin(ApiKeyProfile, ApiKey.owner_id == ApiKeyProfile.user_id)
            .filter(PackageVersion.channel_name == package.channel_name)
            .filter(PackageVersion.package_name == package.name)
        )

        if time_created_ge:
            query = query.filter(PackageVersion.time_created >= time_created_ge)

        return query.all()

    def is_active_platform(self, channel_name: str, platform: str):
        if platform == 'noarch':
            return True

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
                PackageVersion.time_modified,
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
