import grp
import logging
import os
import pwd
from typing import List, Optional

import pamela
from fastapi import Request

from quetz.authentication.base import SimpleAuthenticator, UserProfile
from quetz.authorization import ServerRole
from quetz.config import Config, ConfigEntry, ConfigSection

logger = logging.getLogger("quetz")


class PAMAuthenticator(SimpleAuthenticator):

    provider: str = 'pam'

    service: str = "login"
    encoding: str = 'utf8'
    check_account: bool = True

    # configure server roles
    admin_groups: List[str] = []
    maintainer_groups: List[str] = []
    member_groups: List[str] = []

    def _make_config(self):
        section = ConfigSection(
            "pamauthenticator",
            [
                ConfigEntry("provider", str, default="pam", required=False),
                ConfigEntry("service", str, default="login", required=False),
                ConfigEntry("encoding", str, default="utf8", required=False),
                ConfigEntry("check_account", bool, default=True, required=False),
                ConfigEntry("admin_groups", list, default=list, required=False),
                ConfigEntry("maintainer_groups", list, default=list, required=False),
                ConfigEntry("member_groups", list, default=list, required=False),
            ],
        )
        return [section]

    def _get_group_id_by_name(self, groupname):
        return grp.getgrnam(groupname).gr_gid

    def _get_user_gid_by_name(self, username):
        return pwd.getpwnam(username).pw_gid

    def _get_group_ids(self, group_names):
        gids = []
        for group in group_names:
            try:
                gids.append(self._get_group_id_by_name(group))
            except Exception as exc:
                logger.warning(f"got error {exc}.  Group {group} may not exist")
        return gids

    def _get_user_group_ids(self, username):
        user_gid = self._get_user_gid_by_name(username)
        return [os.getgrouplist(username, user_gid)]

    def configure(self, config: Config):

        config_options = self._make_config()
        config.register(config_options)

        if config.configured_section("pamauthenticator"):
            self.provider = config.pamauthenticator_provider
            self.service = config.pamauthenticator_service
            self.encoding = config.pamauthenticator_encoding
            self.check_account = config.pamauthenticator_check_account
            self.admin_groups = config.pamauthenticator_admin_groups
            self.maintainer_groups = config.pamauthenticator_maintainer_groups
            self.member_groups = config.pamauthenticator_member_groups
            self.is_enabled = True
        else:
            self.is_enabled = False

        super().configure(config)

    def user_role(self, request: Request, profile: UserProfile):

        mappings = [
            (ServerRole.OWNER, self.admin_groups),
            (ServerRole.MAINTAINER, self.maintainer_groups),
            (ServerRole.MEMBER, self.member_groups),
        ]
        username = profile["login"]

        user_gids = self._get_user_group_ids(username)

        for role, groups in mappings:
            role_gids = self._get_group_ids(groups)
            if set(role_gids) & set(user_gids):
                return role.value

    async def authenticate(
        self,
        request: Request,
        data: Optional[dict] = None,
        dao=None,
        config=None,
        **kwargs,
    ) -> Optional[str]:
        """Authenticate with PAM, and return the username if login is successful.
        Return None otherwise.
        """
        if data is None:
            return None

        username = data['username']
        try:
            pamela.authenticate(
                username, data['password'], service=self.service, encoding=self.encoding
            )
        except pamela.PAMError as e:
            logger.warning(
                "PAM Authentication failed (%s@%s): %s",
                username,
                request.client.host,
                e,
            )
            return None

        if self.check_account:
            try:
                pamela.check_account(
                    username, service=self.service, encoding=self.encoding
                )
            except pamela.PAMError as e:
                logger.warning(
                    "PAM Account Check failed (%s@%s): %s",
                    username,
                    request.client.host,
                    e,
                )
                return None

        return username
