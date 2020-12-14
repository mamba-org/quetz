# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session, aliased, joinedload

from quetz import channel_data, errors, rest_models, versionorder
from quetz.utils import apply_custom_query

from .db_models import (
    ApiKey,
    Channel,
    ChannelMember,
    Identity,
    Package,
    PackageMember,
    PackageVersion,
    Profile,
    User,
)
from .jobs.models import Job

logger = logging.getLogger("quetz")


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
    db: Session

    def __init__(self, db: Session):
        self.db = db

    def rollback(self):
        self.db.rollback()

    def get_profile(self, user_id):
        return self.db.query(Profile).filter(Profile.user_id == user_id).one()

    def get_user(self, user_id):
        return self.db.query(User).filter(User.id == user_id).one()

    def get_users(self, skip: int, limit: int, q: str):
        query = (
            self.db.query(User)
            .filter(User.username.isnot(None))
            .filter(User.profile.has())
        )

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

    def delete_user(self, user_id: bytes):
        # we are not really removing users
        # only their identity providers and profiles
        self.db.query(Profile).filter(Profile.user_id == user_id).delete()
        self.db.query(Identity).filter(Identity.user_id == user_id).delete()
        self.db.query(ApiKey).filter(
            or_(ApiKey.user_id == user_id, ApiKey.owner_id == user_id)
        ).delete()
        self.db.commit()

    def set_user_role(self, username: str, role: str):
        user = self.db.query(User).filter(User.username == username).one_or_none()

        if user:
            user.role = role
            self.db.commit()

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

    def create_channel(
        self,
        data: rest_models.Channel,
        user_id: Optional[bytes],
        role: Optional[str],
        size_limit: Optional[int] = None,
    ):
        channel = Channel(
            name=data.name,
            description=data.description,
            mirror_channel_url=data.mirror_channel_url,
            mirror_mode=data.mirror_mode,
            private=data.private,
            size_limit=size_limit,
        )

        self.db.add(channel)

        if role and user_id:
            member = ChannelMember(channel=channel, user_id=user_id, role=role)
            self.db.add(member)

        self.db.commit()

        return channel

    def update_channel(self, channel_name, data: dict):

        self.db.query(Channel).filter(Channel.name == channel_name).update(
            data, synchronize_session=False
        )
        self.db.commit()

    def delete_channel(self, channel_name):
        channel = self.get_channel(channel_name)

        self.db.delete(channel)
        self.db.commit()

    def get_packages(self, channel_name: str, skip: int, limit: int, q: Optional[str]):
        query = self.db.query(Package).filter(Package.channel_name == channel_name)

        if q:
            query = query.filter(Package.name.like(f'%{q}%'))

        if limit < 0:
            return query.all()

        return get_paginated_result(query, skip, limit)

    def search_packages(
        self,
        keywords: List[str],
        filters: Optional[List[tuple]],
        user_id: Optional[bytes],
    ):
        db = self.db.query(Package).join(Channel).join(PackageVersion)
        query = apply_custom_query('package', db, keywords, filters)
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

    def search_channels(
        self,
        keywords: List[str],
        filters: Optional[List[tuple]],
        user_id: Optional[bytes],
    ):
        db = self.db.query(Channel)
        query = apply_custom_query('channel', db, keywords, filters)
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

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise errors.DBError(str(exc))

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
            .filter(User.username.isnot(None))
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

    def get_api_keys_with_members(self, user_id):
        return (
            self.db.query(ApiKey, PackageMember, ChannelMember)
            .select_from(ApiKey)
            .filter(ApiKey.owner_id == user_id)
            .filter(~ApiKey.deleted)
            .outerjoin(ChannelMember, ChannelMember.user_id == ApiKey.user_id)
            .outerjoin(PackageMember, PackageMember.user_id == ApiKey.user_id)
            .all()
        )

    def get_package_api_keys(self, user_id):
        return (
            self.db.query(PackageMember, ApiKey)
            .join(User, PackageMember.user_id == User.id)
            .join(ApiKey, ApiKey.user_id == User.id)
            .filter(ApiKey.owner_id == user_id)
            .filter(~ApiKey.deleted)
            .all()
        )

    def get_channel_api_keys(self, user_id):
        return (
            self.db.query(ChannelMember, ApiKey)
            .join(User, ChannelMember.user_id == User.id)
            .join(ApiKey, ApiKey.user_id == User.id)
            .filter(ApiKey.owner_id == user_id)
            .filter(~ApiKey.deleted)
            .all()
        )

    def create_api_key(self, user_id, api_key: rest_models.BaseApiKey, key):
        owner = self.get_user(user_id)
        # if no roles are passed, create an API key with the same permissions as user
        if not api_key.roles:
            user = owner
        else:
            user = User(id=uuid.uuid4().bytes)
            self.db.add(user)
        db_api_key = ApiKey(
            key=key, description=api_key.description, user=user, owner=owner
        )

        self.db.add(db_api_key)
        for role in api_key.roles:
            if role.package:
                package_member = (
                    self.db.query(PackageMember)
                    .filter_by(
                        user=user, channel_name=role.channel, package_name=role.package
                    )
                    .one_or_none()
                )
                if not package_member:
                    package_member = PackageMember(
                        user=user,
                        channel_name=role.channel,
                        package_name=role.package,
                        role=role.role,
                    )
                    self.db.add(package_member)
                else:
                    package_member.role = role.role
            else:
                channel_member = (
                    self.db.query(ChannelMember)
                    .filter_by(user=user, channel_name=role.channel)
                    .one_or_none()
                )
                if not channel_member:
                    channel_member = ChannelMember(
                        user=user, channel_name=role.channel, role=role.role
                    )
                    self.db.add(channel_member)
                else:
                    channel_member.role = role.role

        self.db.commit()

        return db_api_key

    def get_api_key(self, key):
        return self.db.query(ApiKey).get(key)

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
        size,
        upsert: bool = False,
    ):
        # hold a lock on the package
        package = (  # noqa
            self.db.query(Package)
            .with_for_update()
            .filter(Package.channel_name == channel_name)
            .filter(Package.name == package_name)
            .filter(PackageVersion.package_format == package_format)
            .filter(PackageVersion.platform == platform)
        ).first()

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

            all_existing_versions = (
                self.db.query(PackageVersion)
                .filter(PackageVersion.channel_name == channel_name)
                .filter(PackageVersion.package_name == package_name)
                .order_by(PackageVersion.version_order.asc())
            ).all()

            version_order = 0

            if all_existing_versions:
                new_version = versionorder.VersionOrder(version)
                for v in all_existing_versions:
                    other = versionorder.VersionOrder(v.version)
                    is_newer = other < new_version or (
                        other == new_version and v.build_number < build_number
                    )
                    if is_newer:
                        break
                version_order = v.version_order if is_newer else v.version_order + 1

                (
                    self.db.query(PackageVersion)
                    .filter(PackageVersion.channel_name == channel_name)
                    .filter(PackageVersion.package_name == package_name)
                    .filter(PackageVersion.package_format == package_format)
                    .filter(PackageVersion.platform == platform)
                    .filter(PackageVersion.version_order >= version_order)
                    .update(
                        {"version_order": PackageVersion.version_order + 1},
                    )
                )

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
                version_order=version_order,
                uploader_id=uploader_id,
                size=size,
            )

            self.db.add(package_version)
            logger.debug(
                f"adding package {package_name} version {version} to "
                + f"channel {channel_name}",
            )

        elif upsert:
            existing_versions.update(
                {
                    "filename": filename,
                    "info": info,
                    "uploader_id": uploader_id,
                    "time_modified": datetime.utcnow(),
                    "size": size,
                },
                synchronize_session="evaluate",
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
            .order_by(PackageVersion.version_order.asc())
        )

        if time_created_ge:
            query = query.filter(PackageVersion.time_created >= time_created_ge)

        return query.all()

    def get_package_version_by_filename(
        self, channel_name: str, package_name: str, filename: str, platform: str
    ):

        query = (
            self.db.query(PackageVersion)
            .filter(PackageVersion.channel_name == channel_name)
            .filter(PackageVersion.package_name == package_name)
            .filter(PackageVersion.filename == filename)
            .filter(PackageVersion.platform == platform)
        )

        return query.one_or_none()

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
            .filter(PackageVersion.platform == subdir)
            .order_by(PackageVersion.filename)
        )

    def get_channel_datas(self, channel_name: str):
        # Returns iterator
        return (
            self.db.query(Package.name, Package.channeldata)
            .filter(Package.channel_name == channel_name)
            .order_by(Package.name)
        )

    def assert_size_limits(self, channel_name: str, size: int):
        channel_size, channel_size_limit = (
            self.db.query(Channel.size, Channel.size_limit)
            .filter(Channel.name == channel_name)
            .one()
        )

        if channel_size_limit is not None:

            allowed = (channel_size + size) <= channel_size_limit

            if not allowed:
                raise errors.QuotaError(
                    f"{channel_name} is above quota of {channel_size_limit} bytes"
                )

    def update_channel_size(self, channel_name: str):

        channel_size = (
            self.db.query(func.sum(PackageVersion.size).label('size'))
            .filter(PackageVersion.channel_name == channel_name)
            .scalar()
        )

        if channel_size is None:
            channel_size = 0

        self.update_channel(channel_name, {"size": channel_size})

    def create_user_with_role(self, user_name: str, role: Optional[str] = None):
        """create a user without a profile or return a user if already exists and replace
        role"""
        user = self.db.query(User).filter(User.username == user_name).one_or_none()
        if not user:
            user = User(id=uuid.uuid4().bytes, username=user_name, role=role)
            self.db.add(user)

        if role:
            user.role = role
        self.db.commit()
        return user

    def create_user_with_profile(
        self,
        username: str,
        provider: str,
        identity_id: str,
        name: str,
        avatar_url: str,
        role: Optional[str],
        exist_ok: bool = False,
    ):
        """create a user with profile and role

        :param exist_ok: flag to check whether the user should be reused if exists
          or raise an error
        """

        user = self.db.query(User).filter(User.username == username).one_or_none()

        if user and not exist_ok:
            raise IntegrityError(f"User {username} exists", "", "")

        if not user:
            user = User(id=uuid.uuid4().bytes, username=username, role=role)

        identity = Identity(
            provider=provider,
            identity_id=identity_id,
            username=username,
        )

        profile = Profile(name=name, avatar_url=avatar_url)

        user.identities.append(identity)
        user.profile = profile
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return user

    def get_jobs(self):
        jobs = self.db.query(Job).all()
        return jobs

    def get_job(self, job_id: int):
        job = self.db.query(Job).filter(Job.id == job_id).one_or_none()
        return job
