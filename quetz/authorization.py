# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import enum
import uuid
from datetime import date
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

import quetz.config

from .db_models import ApiKey, ChannelMember, PackageMember, User

OWNER = "owner"
MAINTAINER = "maintainer"
MEMBER = "member"

SERVER_OWNER = OWNER
SERVER_MAINTAINER = MAINTAINER
SERVER_MEMBER = MEMBER
SERVER_USER = None

ROLES = [OWNER, MAINTAINER, MEMBER]


class ServerRole(str, enum.Enum):
    OWNER = OWNER
    MAINTAINER = MAINTAINER
    MEMBER = MEMBER
    USER = None


class Rules:
    def __init__(self, API_key: Optional[str], session: dict, db: Session):
        self.API_key = API_key
        self.session = session
        self.db = db

    def get_user(self) -> Optional[bytes]:
        user_id = None

        if self.API_key:
            api_key = (
                self.db.query(ApiKey)
                .filter(ApiKey.key == self.API_key, ~ApiKey.deleted)
                .filter(
                    ApiKey.key == self.API_key,
                    or_(ApiKey.expire_at >= date.today(), ApiKey.expire_at.is_(None)),
                )
                .one_or_none()
            )
            if api_key:
                user_id = api_key.user_id
        else:
            user_id = self.session.get("user_id")
            if user_id:
                user_id = uuid.UUID(user_id).bytes

        return user_id

    def assert_user(self) -> bytes:
        user_id = self.get_user()

        if not user_id or not self.db.query(User).filter(User.id == user_id).count():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not logged in",
            )

        return user_id

    def assert_read_user_data(self, requested_user_id: bytes):

        user_id = self.assert_user()

        if not (requested_user_id == user_id):
            self.assert_server_roles([SERVER_OWNER, SERVER_MAINTAINER])

        return user_id

    def assert_delete_user(self, requested_user_id: bytes):

        user_id = self.assert_user()

        if not (requested_user_id == user_id):
            self.assert_server_roles([SERVER_OWNER, SERVER_MAINTAINER])

        return user_id

    def assert_assign_user_role(self, role: str):

        if role == SERVER_MAINTAINER or role == SERVER_OWNER:
            return self.assert_server_roles([SERVER_OWNER])
        if role == SERVER_MEMBER:
            return self.assert_server_roles([SERVER_OWNER, SERVER_MAINTAINER])

    def assert_server_roles(self, roles: list, msg: Optional[str] = None):
        user_id = self.assert_user()

        if not self.has_server_roles(user_id, roles):

            detail = (
                msg or "this operation requires " + " or ".join(roles) + " roles",
            )

            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

        return user_id

    def has_server_roles(self, user_id, roles: list):
        pm = quetz.config.get_plugin_manager()
        res = self.db.query(User).filter(User.id == user_id).one_or_none()

        if res:
            user_role = res.role
            if user_role in roles:
                permissions_check = pm.hook.check_additional_permissions(
                    db=self.db, user_id=user_id, user_role=user_role
                )
                if len(permissions_check):
                    if all(permissions_check):
                        return res
                    else:
                        return None
                else:
                    return res
            else:
                return None
        else:
            return None

    def has_channel_role(self, user_id: bytes, channel_name: str, roles: list):
        return (
            self.db.query(ChannelMember)
            .filter(ChannelMember.user_id == user_id)
            .filter(ChannelMember.channel_name == channel_name)
            .filter(ChannelMember.role.in_(roles))
            .one_or_none()
        )

    def has_package_role(
        self, user_id, channel_name: str, package_name: str, roles: list
    ):
        return (
            self.db.query(PackageMember)
            .filter(PackageMember.user_id == user_id)
            .filter(PackageMember.channel_name == channel_name)
            .filter(PackageMember.package_name == package_name)
            .filter(PackageMember.role.in_(roles))
            .one_or_none()
        )

    def has_channel_or_package_roles(
        self,
        user_id,
        channel_name: str,
        channel_roles: list,
        package_name: str,
        package_roles: list,
    ):
        return (
            self.is_user_elevated(user_id)
            or self.has_channel_role(user_id, channel_name, channel_roles)
            or self.has_package_role(user_id, channel_name, package_name, package_roles)
        )

    def is_user_elevated(self, user_id):
        return self.has_server_roles(user_id, [SERVER_OWNER, SERVER_MAINTAINER])

    def assert_channel_roles(self, channel_name: str, channel_roles: list):
        user_id = self.assert_user()

        if not (
            self.is_user_elevated(user_id)
            or self.has_channel_role(user_id, channel_name, channel_roles)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No permission"
            )

    def assert_channel_or_package_roles(
        self,
        channel_name: str,
        channel_roles: list,
        package_name: str,
        package_roles: list,
    ):
        user_id = self.assert_user()

        if not self.has_channel_or_package_roles(
            user_id, channel_name, channel_roles, package_name, package_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No permission"
            )

    def assert_add_channel_member(self, channel_name: str, role: str):
        self.assert_channel_roles(channel_name, [OWNER])

    def assert_remove_channel_member(self, channel_name: str, role: str):
        self.assert_channel_roles(channel_name, [OWNER])

    def assert_add_package_member(self, channel_name, package_name, role):
        self.assert_channel_or_package_roles(
            channel_name, [OWNER, MAINTAINER], package_name, [OWNER]
        )

    def assert_create_api_key_roles(self, roles):
        for role in roles:
            if role.package:
                required_package_role = (
                    [OWNER] if role.role == OWNER else [OWNER, MAINTAINER]
                )
                self.assert_channel_or_package_roles(
                    role.channel,
                    [OWNER, MAINTAINER],
                    role.package,
                    required_package_role,
                )
            elif role.channel:
                required_channel_roles = (
                    [OWNER] if role.role == OWNER else [OWNER, MAINTAINER]
                )
                self.assert_channel_roles(role.channel, required_channel_roles)
            else:
                # create key without assigning special channel/package privilages
                return True

    def assert_delete_api_key(self, api_key):

        user_id = self.assert_user()

        if (
            not self.is_user_elevated(user_id)
            and not api_key.user_id == user_id
            and not api_key.owner_id == user_id
        ):

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No permission"
            )

    def assert_upload_file(self, channel_name, package_name):
        self.assert_channel_or_package_roles(
            channel_name, [OWNER, MAINTAINER], package_name, [OWNER, MAINTAINER]
        )

    def assert_create_mirror_channel(self):

        self.assert_server_roles([SERVER_OWNER, SERVER_MAINTAINER])

    def assert_create_channel(self):

        self.assert_server_roles([SERVER_OWNER, SERVER_MAINTAINER, SERVER_MEMBER])

    def assert_update_channel_info(self, channel_name: str):

        self.assert_channel_roles(channel_name, [OWNER, MAINTAINER])

    def assert_register_mirror(self, channel_name: str):

        self.assert_channel_roles(channel_name, [OWNER, MAINTAINER])

    def assert_unregister_mirror(self, channel_name: str):

        self.assert_register_mirror(channel_name)

    def assert_create_package(self, channel_name: str):

        self.assert_channel_roles(channel_name, [OWNER, MAINTAINER])

    def assert_create_proxy_channel(self):

        self.assert_server_roles([SERVER_OWNER, SERVER_MAINTAINER])

    def assert_list_channel_members(self, channel_name: str):

        self.assert_channel_roles(channel_name, [OWNER, MAINTAINER])

    def assert_synchronize_mirror(self, channel_name):
        self.assert_channel_roles(channel_name, [OWNER, MAINTAINER])

    def assert_reindex_channel(self, channel_name):
        self.assert_channel_roles(channel_name, [OWNER, MAINTAINER])

    def assert_validate_package_cache(self, channel_name):
        self.assert_server_roles([SERVER_OWNER, SERVER_MAINTAINER])

    def assert_overwrite_package_version(self, channel_name, package_name):
        self.assert_channel_or_package_roles(
            channel_name, [OWNER], package_name, [OWNER]
        )

    def assert_delete_channel(self, channel):
        self.assert_channel_roles(channel.name, [OWNER, MAINTAINER])

    def assert_channel_read(self, channel):
        if channel.private:
            self.assert_channel_roles(channel.name, [OWNER, MAINTAINER, MEMBER])

    def assert_set_channel_size_limit(self):

        self.assert_server_roles(
            [SERVER_OWNER, SERVER_MAINTAINER],
            msg="only server maintainer or owner can set channel size limit",
        )

    def assert_channel_db_cleanup(self, channel_name):
        self.assert_channel_roles(channel_name, [OWNER])

    def assert_package_read(self, package):
        if package.channel.private:
            self.assert_channel_or_package_roles(
                package.channel_name,
                [OWNER, MAINTAINER, MEMBER],
                package.name,
                [OWNER, MAINTAINER, MEMBER],
            )

    def assert_package_write(self, package):
        self.assert_channel_or_package_roles(
            package.channel_name, [OWNER, MAINTAINER], package.name, [OWNER, MAINTAINER]
        )

    def assert_package_delete(self, package):
        self.assert_channel_or_package_roles(
            package.channel_name, [OWNER, MAINTAINER], package.name, [OWNER, MAINTAINER]
        )

    def assert_jobs(self, owner_id: Optional[bytes] = None):
        user_id = self.assert_user()
        if not self.is_user_elevated(user_id):
            if not owner_id or user_id != owner_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not allowed",
                )
