# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .db_models import ApiKey, ChannelMember, PackageMember, User

OWNER = 'owner'
MAINTAINER = 'maintainer'
MEMBER = 'member'

ROLES = [OWNER, MAINTAINER, MEMBER]


class Rules:
    def __init__(self, API_key: str, session: dict, db: Session):
        self.API_key = API_key
        self.session = session
        self.db = db

    def get_user(self) -> Optional[bytes]:
        user_id = None

        if self.API_key:
            api_key = (
                self.db.query(ApiKey).filter(ApiKey.key == self.API_key).one_or_none()
            )
            if api_key:
                user_id = api_key.user_id
        else:
            user_id = self.session.get('user_id')
            if user_id:
                user_id = uuid.UUID(user_id).bytes

        return user_id

    def assert_user(self) -> bytes:
        user_id = self.get_user()

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Not logged in',
            )

        return user_id

    def assert_read_user_role(self, requested_user_id):

        user_id = self.assert_user()

        if not (requested_user_id == user_id):
            self.assert_server_roles([OWNER, MAINTAINER])

    def assert_assign_user_role(self, role: str):

        if role == MAINTAINER or role == OWNER:
            self.assert_server_roles([OWNER])
        if role == MEMBER:
            self.assert_server_roles([OWNER, MAINTAINER])

    def assert_server_roles(self, roles: list):
        user_id = self.assert_user()

        if not self.has_server_roles(user_id, roles):

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='this operation requires' + " or ".join(roles) + ' roles',
            )

    def has_server_roles(self, user_id, roles: list):

        return (
            self.db.query(User)
            .filter(User.id == user_id)
            .filter(User.role.in_(roles))
            .one_or_none()
        )

    def has_channel_role(self, user_id, channel_name: str, roles: list):
        return (
            self.db.query(ChannelMember)
            .filter(ChannelMember.user_id == user_id)
            .filter(ChannelMember.channel_name == channel_name)
            .filter(ChannelMember.role.in_(roles))
            .one_or_none()
        )

    def require_channel_role(self, channel_name: str, roles: list):
        user_id = self.assert_user()

        if not self.has_channel_role(user_id, channel_name, roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail='No permission'
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
        return self.has_channel_role(
            user_id, channel_name, channel_roles
        ) or self.has_package_role(user_id, channel_name, package_name, package_roles)

    def assert_channel_roles(self, channel_name: str, channel_roles: list):
        user_id = self.assert_user()

        if not self.has_channel_role(user_id, channel_name, channel_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail='No permission'
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
                status_code=status.HTTP_403_FORBIDDEN, detail='No permission'
            )

    def assert_add_channel_member(self, channel_name: str, role: str):
        self.require_channel_role(channel_name, [OWNER])

    def assert_remove_channel_member(self, channel_name: str, role: str):
        self.require_channel_role(channel_name, [OWNER])

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

    def assert_upload_file(self, channel_name, package_name):
        self.assert_channel_or_package_roles(
            channel_name, [OWNER, MAINTAINER], package_name, [OWNER, MAINTAINER]
        )

    def assert_create_mirror_channel(self):

        self.assert_server_roles([OWNER, MAINTAINER])

    def assert_create_proxy_channel(self):

        self.assert_server_roles([OWNER, MAINTAINER])

    def assert_synchronize_mirror(self, channel_name):
        self.assert_channel_roles(channel_name, [OWNER, MAINTAINER])

    def assert_overwrite_package_version(self, channel_name, package_name):
        self.assert_channel_or_package_roles(
            channel_name, [OWNER], package_name, [OWNER]
        )

    def assert_channel_read(self, channel):
        if channel.private:
            self.assert_channel_roles(channel.name, [OWNER, MAINTAINER, MEMBER])
