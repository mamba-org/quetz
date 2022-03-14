# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import json
import logging
import uuid
from collections import defaultdict
from datetime import date, datetime
from itertools import groupby
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import and_, func, insert, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Query, Session, aliased, exc, joinedload
from sqlalchemy.sql.expression import FunctionElement, Insert
from sqlalchemy.types import DateTime

from quetz import channel_data, errors, rest_models, versionorder
from quetz.database_extensions import version_match
from quetz.utils import apply_custom_query

from .db_models import (
    ApiKey,
    Channel,
    ChannelMember,
    ChannelMirror,
    Email,
    Identity,
    Package,
    PackageMember,
    PackageVersion,
    Profile,
    User,
)
from .jobs.models import Job, JobStatus, Task, TaskStatus
from .metrics.db_models import (
    IntervalType,
    PackageVersionMetric,
    next_timestamp,
    round_timestamp,
)

if TYPE_CHECKING:
    from quetz.authentication import base as auth_base

logger = logging.getLogger("quetz")


class date_trunc(FunctionElement):
    """round timestamp to nearest starting edge of an interval

    Arguments
    ---------

    interval: IntervalEnum

    timestamp: datetime
    """

    name = "date_trunc"
    type = DateTime()


@compiles(date_trunc, 'postgresql')
def pg_date_trunc(element, compiler, **kw):
    pg_map = {"H": "hour", "D": "day", "M": "month", "Y": "year"}
    period, date = list(element.clauses)
    return "date_trunc('%s', %s)" % (
        pg_map[period.value.value],
        compiler.process(date, **kw),
    )


@compiles(date_trunc, 'sqlite')
def sqlite_date_trunc(element, compiler, **kw):
    period, date = list(element.clauses)
    now_interval = round_timestamp(date.value, period.value)
    date.value = now_interval
    return compiler.process(date)


class Upsert(Insert):
    """Upsert for PackageVersionMetrics table. Requires a unique
    constraint to be defined.

    Arguments
    ---------

    table

    values: values to insert

    index_elements: columns of unique constraint

    column: Column to be incremented

    incr: increment
    """

    inherit_cache = False

    def __init__(self, table, values, index_elements, column, incr=1):
        self.values = values
        self.index_elements = index_elements
        self.column = column
        self._returning = None
        self.table = table
        self.incr = incr
        self._inline = False


@compiles(Upsert, 'postgresql')
def upsert_pg(element, compiler, **kw):

    index_elements = element.index_elements
    values = element.values
    column = element.column
    incr = element.incr
    table = element.table

    stmt = pg_insert(table).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=index_elements,
        set_={column.name: column + incr},
    )

    return compiler.visit_insert(stmt)


@compiles(Upsert, 'sqlite')
def upsert_sql(element, compiler, **kw):
    # on_conflict_do_update does exist in sqlite
    # but it was ported to sqlalchemy only in version 1.4
    # which was not released at the time of implementing this
    # so we treat it with raw SQL syntax
    # sqlite ref: https://www.sqlite.org/lang_upsert.html
    # sqlalchemy 1.4 ref: https://docs.sqlalchemy.org/en/14/dialects/sqlite.html#insert-on-conflict-upsert # noqa

    index_elements = element.index_elements
    values = element.values
    column = element.column
    incr = element.incr
    table = element.table

    stmt = insert(table).values(values)
    raw_sql = compiler.process(stmt)
    upsert_stmt = "ON CONFLICT ({}) DO UPDATE SET {}={}+{}".format(
        ",".join(index_elements), column.name, column.name, incr
    )

    return raw_sql + " " + upsert_stmt


def get_paginated_result(query: Query, skip: int, limit: int):
    count = query.order_by(None).count()
    query = query.offset(skip)
    if limit >= 0:
        query = query.limit(limit)
    return {
        'pagination': {'skip': skip, 'limit': limit, 'all_records_count': count},
        'result': query.all(),
    }


def _parse_sort_by(query, model, sortstr: str):
    sorts = sortstr.split(',')

    for s in sorts:
        splitted = s.split(':')
        if len(splitted) == 2:
            field, order = splitted
        else:
            field = s
            order = 'desc'

        if hasattr(model, field):
            model_field = getattr(model, field)
            if order == 'desc':
                query = query.order_by(model_field.desc())
            else:
                query = query.order_by(model_field.asc())
    return query


class Dao:
    db: Session

    def __init__(self, db: Session):
        self.db = db

    def rollback(self):
        self.db.rollback()

    def get_profile(self, user_id):
        try:
            return self.db.query(Profile).filter(Profile.user_id == user_id).one()
        except exc.NoResultFound:
            logger.error("User not found")

    def get_user(self, user_id):
        try:
            return self.db.query(User).filter(User.id == user_id).one()
        except exc.NoResultFound:
            logger.error("User not found")

    def get_users(self, skip: int, limit: int, q: str, order_by: str = 'username:asc'):
        query = (
            self.db.query(User)
            .filter(User.username.isnot(None))
            .filter(User.profile.has())
        )

        if q:
            query = query.filter(User.username.ilike(f'%{q}%'))

        query = query.options(joinedload(User.profile))

        if order_by:
            query = _parse_sort_by(query, User, order_by)

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
        self,
        skip: int,
        limit: int,
        q: Optional[str],
        user_id: Optional[bytes],
        include_public: bool = True,
    ):
        query = self.db.query(Channel)

        if user_id:
            if include_public:
                query = query.filter(
                    or_(
                        ~Channel.private,
                        Channel.members.any(ChannelMember.user_id == user_id),
                    )
                )
            else:
                query = query.filter(
                    Channel.members.any(ChannelMember.user_id == user_id)
                )
        else:
            query = query.filter(Channel.private == False)  # noqa

        if q:
            query = query.filter(Channel.name.ilike(f'%{q}%'))

        if limit < 0:
            return query.all()

        return get_paginated_result(query, skip, limit)

    def get_user_channels_with_role(
        self,
        skip: int,
        limit: int,
        user_id: bytes,
    ):
        query = (
            self.db.query(Channel.name, ChannelMember.role)
            .join(ChannelMember)
            .filter(ChannelMember.user_id == user_id)
        )

        if limit < 0:
            return query.all()

        return get_paginated_result(query, skip, limit)

    def create_channel(
        self,
        data: rest_models.Channel,
        user_id: Optional[bytes] = None,
        role: Optional[str] = None,
        size_limit: Optional[int] = None,
    ):
        if '_' in data.name:
            raise errors.ValidationError("_ should not be used in channel name")
        if not data.name.isascii():
            raise errors.ValidationError(
                "only ASCII characters should be used in channel name"
            )

        channel = Channel(
            name=data.name,
            description=data.description,
            mirror_channel_url=data.mirror_channel_url,
            mirror_mode=data.mirror_mode,
            private=data.private,
            ttl=data.ttl,
            channel_metadata=json.dumps(data.metadata.__dict__),
            size_limit=size_limit,
        )

        self.db.add(channel)

        if role and user_id:
            member = ChannelMember(channel=channel, user_id=user_id, role=role)
            self.db.add(member)

        self.db.commit()

        return channel

    def cleanup_channel_db(self, channel_name: str, dry_run: bool = False):
        # remove all Packages without PackageVersions
        package_without_package_versions = []
        all_packages = self.db.query(Package).filter(
            Package.channel_name == channel_name
        )
        for each_package in all_packages:
            all_package_versions = (
                self.db.query(PackageVersion)
                .filter(PackageVersion.channel_name == channel_name)
                .filter(PackageVersion.package_name == each_package.name)
            )
            if all_package_versions.count() == 0:
                package_without_package_versions.append(each_package.name)

        for each_package_name in package_without_package_versions:
            if not dry_run:
                self.db.query(PackageMember).filter(
                    PackageMember.channel_name == channel_name
                ).filter(PackageMember.package_name == each_package_name).delete()

                self.db.query(Package).filter(
                    Package.channel_name == channel_name
                ).filter(Package.name == each_package_name).delete()

            logger.info(
                f"removing Package {channel_name}/{each_package_name} from db as "
                "it has no PackageVersions"
            )

        if not dry_run:
            self.db.commit()

        # clean platforms / channeldata for Packages
        all_packages = self.db.query(Package).filter(
            Package.channel_name == channel_name
        )
        for each_package in all_packages:
            if each_package.channeldata is not None:
                each_package_channeldata = json.loads(each_package.channeldata)
                subdirs = each_package_channeldata["subdirs"]
                if subdirs:
                    if not dry_run:
                        subdirs = sorted(list(set(subdirs)))
                        each_package_channeldata["subdirs"] = subdirs
                        each_package.channeldata = json.dumps(each_package_channeldata)
                        each_package.url = each_package_channeldata.get("home", "")
                        each_package.platforms = ":".join(
                            each_package_channeldata.get("subdirs", [])
                        )
                    logger.info(
                        "cleaning platforms and "
                        f"channeldata for {channel_name}/{each_package.name}"
                    )

        if not dry_run:
            self.db.commit()
        logger.info(f"Done cleaning up db for {channel_name}")

        # Re-sort all PackageVersions
        all_packages = self.db.query(Package).filter(
            Package.channel_name == channel_name
        )
        for x, each_package in enumerate(all_packages):
            all_versions_for_each_package = (
                self.db.query(PackageVersion)
                .filter(PackageVersion.channel_name == channel_name)
                .filter(PackageVersion.package_name == each_package.name)
                .order_by(PackageVersion.version_order.asc())
            ).all()

            if not dry_run:
                v_dict = {}
                for each_package_version in all_versions_for_each_package:
                    if each_package_version.version is not None:
                        v_dict[each_package_version] = versionorder.VersionOrder(
                            each_package_version.version
                        )
                sorted_v = sorted(
                    v_dict.items(), key=lambda item: item[1], reverse=True
                )

                for i, (each_package_version, version) in enumerate(sorted_v):
                    each_package_version.version_order = i
            logger.info(
                f"Re-sorted PackageVersions for {channel_name}/{each_package.name}"
            )

        if not dry_run:
            self.db.commit()
        logger.info(f"Done sorting package versions for {channel_name}")

    def create_channel_mirror(
        self, channel_name: str, url: str, api_endpoint: str, metrics_endpoint: str
    ):

        channel_mirror = ChannelMirror(
            channel_name=channel_name,
            url=url,
            api_endpoint=api_endpoint,
            metrics_endpoint=metrics_endpoint,
        )
        self.db.add(channel_mirror)
        self.db.commit()

        return channel_mirror

    def delete_channel_mirror(self, channel_name: str, mirror_id: str):
        mirror_uuid = uuid.UUID(mirror_id).bytes
        self.db.query(ChannelMirror).filter(ChannelMirror.id == mirror_uuid).filter(
            ChannelMirror.channel_name == channel_name
        ).delete()
        self.db.commit()

    def update_channel(self, channel_name, data: dict):

        self.db.query(Channel).filter(Channel.name == channel_name).update(
            data, synchronize_session=False
        )
        self.db.commit()

    def delete_channel(self, channel_name):
        channel = self.get_channel(channel_name)

        self.db.delete(channel)
        self.db.commit()

    def get_packages(
        self,
        channel_name: str,
        skip: int,
        limit: int,
        q: Optional[str] = None,
        order_by: Optional[str] = None,
    ):

        query = self.db.query(Package).filter(Package.channel_name == channel_name)

        if q:
            query = query.filter(Package.name.like(f'%{q}%'))

        if limit < 0:
            return query.all()

        if not order_by:
            query = query.order_by(Package.name.asc())
        else:
            orders = order_by.split(',')
            for o in orders:
                if o.startswith('latest_change'):
                    query = query.join(Package.current_package_version)
                    if len(o.split(':')) == 2 and o.split(':') == 'desc':
                        query = query.order_by(PackageVersion.time_created.desc())
                    else:
                        query = query.order_by(PackageVersion.time_created.asc())
                else:
                    query = _parse_sort_by(query, Package, order_by)

        return get_paginated_result(query, skip, limit)

    def get_user_packages(self, skip: int, limit: int, user_id: bytes):
        query = (
            self.db.query(Package.name, Package.channel_name, PackageMember.role)
            .join(PackageMember)
            .filter(PackageMember.user_id == user_id)
        )

        if limit < 0:
            return query.all()

        return get_paginated_result(query, skip, limit)

    def search_packages(
        self,
        keywords: List[str],
        filters: Optional[List[tuple]],
        user_id: Optional[bytes],
        order_by: str = 'name:asc',
    ):
        db = self.db.query(Package).join(Channel)
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

        if order_by:
            query = _parse_sort_by(query, Package, order_by)

        return query.all()

    def search_channels(
        self,
        keywords: List[str],
        filters: Optional[List[tuple]],
        user_id: Optional[bytes],
        order_by: str = 'name:asc',
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

        if order_by:
            query = _parse_sort_by(query, Channel, order_by)

        return query.all()

    def get_channel(self, channel_name: str) -> Optional[Channel]:
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
        package.url = data.get("home", "")
        package.platforms = ":".join(data.get("subdirs", []))
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

    def get_api_keys_with_members(self, user_id, api_key_id=None):

        user_role_api_keys = (
            self.db.query(ApiKey)
            .filter(ApiKey.owner_id == user_id)
            .filter(ApiKey.user_id == user_id)
            .filter(~ApiKey.deleted)
        )

        custom_role_api_keys = (
            self.db.query(ApiKey, PackageMember, ChannelMember)
            .filter(ApiKey.owner_id == user_id)
            .filter(~ApiKey.deleted)
            .outerjoin(Profile, ApiKey.user_id == Profile.user_id)
            .filter(Profile.name.is_(None))
            .outerjoin(ChannelMember, ChannelMember.user_id == ApiKey.user_id)
            .outerjoin(PackageMember, PackageMember.user_id == ApiKey.user_id)
        )

        if api_key_id:
            user_role_api_keys = user_role_api_keys.filter(ApiKey.key == api_key_id)
            custom_role_api_keys = custom_role_api_keys.filter(ApiKey.key == api_key_id)

        user_role_api_keys = user_role_api_keys.all()
        custom_role_api_keys = custom_role_api_keys.all()

        return user_role_api_keys, custom_role_api_keys

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
            key=key,
            description=api_key.description,
            time_created=date.today(),
            expire_at=api_key.expire_at,
            user=user,
            owner=owner,
        )

        self.db.add(db_api_key)
        if api_key.roles is not None:
            for role in api_key.roles:
                if role.package:
                    package_member = (
                        self.db.query(PackageMember)
                        .filter_by(
                            user=user,
                            channel_name=role.channel,
                            package_name=role.package,
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
            .join(PackageVersion)
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
                    # type checker justly complains that v.version could be None
                    # ignoring it before attempting true fix
                    other = versionorder.VersionOrder(v.version)  # type: ignore
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

    def get_package_versions(
        self, package, time_created_ge: datetime = None, version_match_str: str = None
    ):
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

        if version_match_str:

            if version_match:
                query = query.filter(
                    version_match(PackageVersion.version, version_match_str)
                )
            else:
                raise NotImplementedError(
                    "Quetz Database extension not loaded. Compile and configure "
                    "database_plugin_path correctly for support!"
                )

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
        emails: Optional[List['auth_base.Email']] = None,
    ):
        """create a user with profile and role

        :param exist_ok: flag to check whether the user should be reused if exists
          or raise an error
        """

        # TODO: check that username comes from the right id provider
        user = self.db.query(User).filter(User.username == username).one_or_none()

        if not exist_ok:
            if user:
                raise IntegrityError(f"User {username} exists", "", "")

            # check if any email already registered
            if emails:
                for e in emails:
                    user_email = (
                        self.db.query(Email)
                        .filter(Email.email == e["email"])
                        .one_or_none()
                    )
                    if user_email:
                        raise IntegrityError(
                            f"User {username} already registered "
                            "with email {user_email.email}",
                            "",
                            "",
                        )

        if not user:
            user = User(id=uuid.uuid4().bytes, username=username, role=role)

        identity = Identity(
            provider=provider,
            identity_id=identity_id,
            username=username,
        )

        profile = Profile(name=name, avatar_url=avatar_url)

        user.identities.append(identity)

        if emails:
            user_emails = []
            for email in emails:
                # we only store verified emails
                if not email["verified"]:
                    continue
                user_email = Email(
                    provider=provider,
                    identity_id=identity_id,
                    email=email["email"],
                    verified=email["verified"],
                    primary=email["primary"],
                )
                user_emails.append(user_email)

            user.emails.extend(user_emails)

        user.profile = profile
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return user

    def get_jobs(
        self,
        states: Optional[List[JobStatus]] = None,
        skip: int = 0,
        limit: int = -1,
        owner_id: Optional[bytes] = None,
    ):
        jobs = self.db.query(Job)

        if states:
            jobs = jobs.filter(Job.status.in_(states))
        if owner_id:
            jobs = jobs.filter(Job.owner_id == owner_id)
        jobs = jobs.order_by(Job.id)

        return get_paginated_result(jobs, skip, limit)

    def get_job(self, job_id: int):
        job = self.db.query(Job).filter(Job.id == job_id).one_or_none()
        return job

    def get_tasks(
        self,
        job_id: int,
        states: Optional[List[TaskStatus]] = None,
        skip: int = 0,
        limit: int = -1,
    ):
        tasks = self.db.query(Task).filter(Task.job_id == job_id)

        if states:
            tasks = tasks.filter(Task.status.in_(states))

        return get_paginated_result(tasks, skip, limit)

    def create_job(self, user_id, job_model):

        serialized = job_model.manifest.encode('ascii')
        job = Job(
            owner_id=user_id,
            manifest=serialized,
            items_spec=job_model.items_spec,
            start_at=job_model.start_at,
            repeat_every_seconds=job_model.repeat_every_seconds,
        )
        self.db.add(job)
        self.db.commit()
        return job

    def incr_download_count(
        self,
        channel: str,
        filename: str,
        platform: str,
        timestamp: Optional[datetime] = None,
        incr: int = 1,
    ):

        metric_name = "download"

        self.db.query(PackageVersion).filter(
            PackageVersion.channel_name == channel
        ).filter(PackageVersion.filename == filename).filter(
            PackageVersion.platform == platform
        ).update(
            {PackageVersion.download_count: PackageVersion.download_count + incr}
        )

        if timestamp is None:
            timestamp = datetime.utcnow()

        all_values = []
        for interval in IntervalType:

            values = {
                'channel_name': channel,
                'platform': platform,
                'metric_name': metric_name,
                'filename': filename,
                "timestamp": date_trunc(interval, timestamp),
                "period": interval,
                "count": incr,
            }

            all_values.append(values)

        index_elements = [
            'channel_name',
            'platform',
            'filename',
            'metric_name',
            'period',
            'timestamp',
        ]

        stmt = Upsert(
            PackageVersionMetric.__table__,
            all_values,
            index_elements,
            PackageVersionMetric.count,
            incr=incr,
        )

        self.db.execute(stmt)

        self.db.commit()

    def get_package_version_metrics(
        self,
        package_version_id,
        period,
        metric_name,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        fill_zeros: bool = False,
    ):

        m = PackageVersionMetric
        v = PackageVersion

        q = (
            self.db.query(m)
            .join(
                v,
                and_(
                    v.platform == m.platform,
                    v.channel_name == m.channel_name,
                    m.filename == v.filename,
                ),
            )
            .filter(v.id == package_version_id)
            .filter(m.period == period)
            .filter(m.metric_name == metric_name)
            .order_by(m.timestamp)
        )

        if start:
            q = q.filter(m.timestamp >= start)

        if end:
            q = q.filter(m.timestamp < end)

        items = q.all()

        if fill_zeros:

            def factory():
                return PackageVersionMetric(
                    count=0,
                    metric_name=metric_name,
                    period=period,
                )

            timestamps: Dict[datetime, PackageVersionMetric] = defaultdict(factory)

            for d in items:
                timestamps[d.timestamp] = d

            start = start or items[0].timestamp
            end = end or items[-1].timestamp

            first = round_timestamp(start, period)
            last = round_timestamp(end, period)

            metrics = []
            while first <= last:
                item = timestamps[first]
                item.timestamp = first
                metrics.append(item)
                first = next_timestamp(first, period)
            return metrics
        else:
            return items

    def get_channel_metrics(
        self,
        channel_name,
        period,
        metric_name,
        platform: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ):

        m = PackageVersionMetric

        q = (
            self.db.query(m)
            .filter(m.channel_name == channel_name)
            .filter(m.period == period)
            .filter(m.metric_name == metric_name)
        )

        if platform:
            q = q.filter(m.platform == platform)

        q = q.order_by(m.platform, m.filename, m.timestamp)

        if start:
            q = q.filter(m.timestamp >= start)

        if end:
            q = q.filter(m.timestamp < end)

        rows_per_filename = groupby(q, key=lambda row: f"{row.platform}/{row.filename}")

        return {
            filename: {"series": list(group)} for filename, group in rows_per_filename
        }
