import getpass
from unittest import mock

import pytest
from fastapi import Request

from quetz.authentication.pam import PAMAuthenticator


@pytest.fixture
def groups():
    return {}


@pytest.fixture
def config_extra(groups):
    return f"""
[pamauthenticator]
admin_groups = {groups.get('admins', [])}
maintainer_groups = {groups.get('maintainers', [])}
member_groups = {groups.get('members', [])}"""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "groups,expected_role",
    [
        (
            {},
            None,
        ),
        (
            {"admins": ["usergroup"]},
            "owner",
        ),
        (
            {"admins": ["usergroup"], "maintainers": ["usergroup"]},
            "owner",
        ),
        (
            {"maintainers": ["usergroup"]},
            "maintainer",
        ),
        (
            {"members": ["usergroup"]},
            "member",
        ),
        pytest.param(
            {"members": ["missinggroup"]},
            None,
            id="missing-group",
        ),
    ],
)
async def test_user_role(config, expected_role):
    auth = PAMAuthenticator(config)
    request = Request(scope={"type": "http"})

    _group_ids = {"usergroup": 1001}
    _user_group_ids = {"quetzuser": [1001, 1002]}

    with mock.patch.multiple(
        auth,
        _get_group_id_by_name=lambda k: _group_ids[k],
        _get_user_group_ids=lambda k: _user_group_ids[k],
    ):
        role = await auth.user_role(request, {"login": "quetzuser"})

    if expected_role is None:
        assert role is None
    else:
        assert role == expected_role


@pytest.mark.asyncio
async def test_authenticate(config):

    auth = PAMAuthenticator(config)
    request = Request(scope={"type": "http"})
    current_user = getpass.getuser()

    result = await auth.authenticate(
        request, {"username": current_user, "password": "test"}
    )

    assert result is None  # authentication failed due to incorrect password
