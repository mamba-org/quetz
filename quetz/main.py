# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.
import datetime
import json
import logging
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from email.utils import formatdate
from tempfile import SpooledTemporaryFile
from typing import List, Optional

import pydantic
import requests
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    responses,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from tenacity import (
    after_log,
    retry,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

from quetz import (
    auth_github,
    auth_google,
    authorization,
    db_models,
    errors,
    exceptions,
    frontend,
    rest_models,
)
from quetz.config import Config, configure_logger, get_plugin_manager
from quetz.dao import Dao
from quetz.deps import (
    get_config,
    get_dao,
    get_db,
    get_remote_session,
    get_rules,
    get_session,
    get_tasks_worker,
)
from quetz.jobs import api as jobs_api
from quetz.metrics.db_models import IntervalType
from quetz.rest_models import ChannelActionEnum, CPRole
from quetz.tasks import indexing
from quetz.tasks.common import Task
from quetz.tasks.mirror import LocalCache, RemoteRepository, get_from_cache_or_download
from quetz.utils import TicToc, generate_random_key, parse_query

from .condainfo import CondaInfo

app = FastAPI()

config = Config()

configure_logger(config)

logger = logging.getLogger("quetz")

app.add_middleware(
    SessionMiddleware,
    secret_key=config.session_secret,
    https_only=config.session_https_only,
)


if config.configured_section("cors"):
    logger.info("Configuring CORS with ")
    logger.info(f"allow_origins     = {config.cors_allow_origins}")
    logger.info(f"allow_credentials = {config.cors_allow_credentials}")
    logger.info(f"allow_methods     = {config.cors_allow_methods}")
    logger.info(f"allow_headers     = {config.cors_allow_headers}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_allow_origins,
        allow_credentials=config.cors_allow_credentials,
        allow_methods=config.cors_allow_methods,
        allow_headers=config.cors_allow_headers,
    )


class CondaTokenMiddleware(BaseHTTPMiddleware):
    """Removes /t/<QUETZ_API_KEY> prefix, adds QUETZ_APY_KEY to the headers and passes
    on the rest of the path to be routed."""

    def __init__(self, app):
        super().__init__(app)
        self.token_pattern = re.compile("^/t/([^/]+?)/")

    async def dispatch(self, request, call_next):
        path = request.scope["path"]
        match = self.token_pattern.search(path)
        if match:
            prefix_length = len(match.group(0)) - 1
            new_path = path[prefix_length:]
            api_key = match.group(1)
            request.scope["path"] = new_path
            request.scope["headers"].append((b"x-api-key", api_key.encode()))

        response = await call_next(request)

        return response


pm = get_plugin_manager()

app.add_middleware(CondaTokenMiddleware)

api_router = APIRouter()

plugin_routers = pm.hook.register_router()

pkgstore = config.get_package_store()
pkgstore_support_url = hasattr(pkgstore, 'url')

if config.configured_section("github"):
    auth_github.register(config)
    app.include_router(auth_github.router)

for router in plugin_routers:
    app.include_router(router)

app.include_router(jobs_api.get_router())

if config.configured_section("google"):
    auth_google.register(config)
    app.include_router(auth_google.router)


class ChannelChecker:
    def __init__(
        self,
        allow_proxy: bool = False,
        allow_mirror: bool = False,
        allow_local: bool = True,
    ):
        self.allow_proxy = allow_proxy
        self.allow_mirror = allow_mirror
        self.allow_local = allow_local

    def __call__(
        self,
        channel_name: str,
        dao: Dao = Depends(get_dao),
        auth: authorization.Rules = Depends(get_rules),
    ) -> db_models.Channel:
        channel = dao.get_channel(channel_name.lower())

        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Channel {channel_name} not found",
            )

        auth.assert_channel_read(channel)

        mirror_url = channel.mirror_channel_url

        is_proxy = mirror_url and channel.mirror_mode == "proxy"
        is_mirror = mirror_url and channel.mirror_mode == "mirror"
        is_local = not mirror_url
        if is_proxy and not self.allow_proxy:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail="This method is not implemented for proxy channels",
            )
        if is_mirror and not self.allow_mirror:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail="This method is not implemented for mirror channels",
            )
        if is_local and not self.allow_local:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail="This method is not implemented for local channels",
            )
        return channel


get_channel_or_fail = ChannelChecker(allow_proxy=False, allow_mirror=True)
get_channel_allow_proxy = ChannelChecker(allow_proxy=True, allow_mirror=True)
get_channel_mirror_only = ChannelChecker(allow_mirror=True, allow_local=False)


def get_package_or_fail(
    package_name: str,
    channel_name: str,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
) -> db_models.Package:

    package = dao.get_package(channel_name.lower(), package_name)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Package {channel_name}/{package_name} not found",
        )

    auth.assert_package_read(package)
    return package


# helper functions


async def check_token_revocation(session):
    valid = True
    identity_provider = session.get("identity_provider")
    if identity_provider == "github":
        valid = await auth_github.validate_token(session.get("token"))
    elif identity_provider == "google":
        valid = await auth_google.validate_token(session.get("token"))
    if not valid:
        logout(session)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not logged in",
        )


def logout(session):
    session.pop("user_id", None)
    session.pop("identity_provider", None)
    session.pop("token", None)


# custom exception handlers
@app.exception_handler(errors.ValidationError)
async def unicorn_exception_handler(request: Request, exc: errors.ValidationError):
    return responses.JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)}
    )


# endpoints
@app.route("/auth/logout")
async def route_logout(request):
    logout(request.session)
    return RedirectResponse("/")


@api_router.get("/dummylogin/{username}", tags=["dev"])
def dummy_login(
    username: str, dao: Dao = Depends(get_dao), session=Depends(get_session)
):
    user = dao.get_user_by_username(username)

    logout(session)
    session["user_id"] = str(uuid.UUID(bytes=user.id))

    session["identity_provider"] = "dummy"
    return RedirectResponse("/")


@api_router.get("/me", response_model=rest_models.Profile, tags=["users"])
async def me(
    session: dict = Depends(get_session),
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    """Returns your quetz profile"""

    # Check if token is still valid
    await check_token_revocation(session)

    user_id = auth.assert_user()

    profile = dao.get_profile(user_id)
    profile.user.id = str(uuid.UUID(bytes=profile.user.id))
    return profile


def get_users_handler(dao, q, auth, skip, limit):

    user_id = auth.assert_user()

    results = dao.get_users(skip, limit, q)

    user_list = results["result"] if "result" in results else results

    if not auth.is_user_elevated(user_id):
        append_user = None
        for user in user_list:
            if user.id == user_id:
                append_user = user
        user_list.clear()
        if append_user:
            user_list.append(append_user)

    return results


@api_router.get("/users", response_model=List[rest_models.User], tags=["users"])
def get_users(
    dao: Dao = Depends(get_dao),
    q: str = None,
    auth: authorization.Rules = Depends(get_rules),
):
    return get_users_handler(dao, q, auth, 0, -1)


@api_router.get(
    "/paginated/users",
    response_model=rest_models.PaginatedResponse[rest_models.User],
    tags=["users"],
)
def get_paginated_users(
    dao: Dao = Depends(get_dao),
    skip: int = 0,
    limit: int = 10,
    q: str = None,
    auth: authorization.Rules = Depends(get_rules),
):
    return get_users_handler(dao, q, auth, skip, limit)


@api_router.get("/users/{username}", response_model=rest_models.User, tags=["users"])
def get_user(
    username: str,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    user = dao.get_user_by_username(username)

    if not user or not user.profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User {username} not found"
        )

    auth.assert_read_user_data(user.id)

    return user


@api_router.delete("/users/{username}", tags=["users"])
def delete_user(
    username: str,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    user = dao.get_user_by_username(username)

    auth.assert_delete_user(user.id)
    dao.delete_user(user.id)


@api_router.get(
    "/users/{username}/role",
    response_model=rest_models.UserRole,
    tags=["users"],
)
def get_user_role(
    username: str,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):

    user = dao.get_user_by_username(username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User {username} not found"
        )

    auth.assert_read_user_data(user.id)

    return {"role": user.role}


@api_router.put("/users/{username}/role", tags=["users"])
def set_user_role(
    username: str,
    role: rest_models.UserRole,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):

    user = dao.get_user_by_username(username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User {username} not found"
        )

    auth.assert_assign_user_role(role.role)

    dao.set_user_role(username, role=role.role)


@api_router.get(
    "/channels", response_model=List[rest_models.ChannelBase], tags=["channels"]
)
def get_channels(
    dao: Dao = Depends(get_dao),
    q: str = None,
    auth: authorization.Rules = Depends(get_rules),
):
    """List all channels"""

    user_id = auth.get_user()
    return dao.get_channels(0, -1, q, user_id)


@api_router.get(
    "/paginated/channels",
    response_model=rest_models.PaginatedResponse[rest_models.ChannelBase],
    tags=["channels"],
)
def get_paginated_channels(
    dao: Dao = Depends(get_dao),
    skip: int = 0,
    limit: int = 10,
    q: str = None,
    auth: authorization.Rules = Depends(get_rules),
):
    """List all channels, as a paginated response"""
    user_id = auth.get_user()
    return dao.get_channels(skip, limit, q, user_id)


@api_router.get(
    "/channels/{channel_name}",
    response_model=rest_models.ChannelBase,
    tags=["channels"],
)
def get_channel(channel: db_models.Channel = Depends(get_channel_allow_proxy)):
    return channel


@api_router.post(
    "/channels/{channel_name}/mirrors",
    status_code=201,
    tags=["channels"],
)
def post_channel_mirror(
    mirror: rest_models.ChannelMirror,
    channel_name: str,
    channel: db_models.Channel = Depends(get_channel_allow_proxy),
    auth: authorization.Rules = Depends(get_rules),
    dao: Dao = Depends(get_dao),
):

    auth.assert_register_mirror(channel_name)

    dao.create_channel_mirror(channel_name, mirror.url)


@api_router.delete(
    "/channels/{channel_name}",
    tags=["channels"],
)
def delete_channel(
    channel: db_models.Channel = Depends(get_channel_allow_proxy),
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):

    auth.assert_delete_channel(channel)
    dao.delete_channel(channel.name)
    files = pkgstore.list_files(channel.name)
    for f in files:
        pkgstore.delete_file(channel.name, destination=f)


@api_router.put("/channels/{channel_name}/actions", tags=["channels"])
def put_mirror_channel_actions(
    action: rest_models.ChannelAction,
    channel: db_models.Channel = Depends(get_channel_allow_proxy),
    dao: Dao = Depends(get_dao),
    task: Task = Depends(get_tasks_worker),
):

    task.execute_channel_action(action.action, channel)


@api_router.post("/channels", status_code=201, tags=["channels"])
def post_channel(
    new_channel: rest_models.Channel,
    background_tasks: BackgroundTasks,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
    task: Task = Depends(get_tasks_worker),
    remote_session: requests.Session = Depends(get_remote_session),
    config=Depends(get_config),
):

    user_id = auth.assert_user()

    channel = dao.get_channel(new_channel.name)

    if channel:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Channel {new_channel.name} exists",
        )

    if not new_channel.mirror_channel_url:
        auth.assert_create_channel()

    is_mirror = new_channel.mirror_channel_url and new_channel.mirror_mode == "mirror"

    is_proxy = new_channel.mirror_channel_url and new_channel.mirror_mode == "proxy"

    if is_mirror:
        auth.assert_create_mirror_channel()

    if is_proxy:
        auth.assert_create_proxy_channel()

    if new_channel.metadata.actions is None:
        if is_mirror:
            actions = [ChannelActionEnum.synchronize]
        else:
            actions = []
    else:
        actions = new_channel.metadata.actions

    user_attrs = new_channel.dict(exclude_unset=True)

    if "size_limit" in user_attrs:
        auth.assert_set_channel_size_limit(channel)
        size_limit = new_channel.size_limit
    else:
        if config.configured_section("quotas"):
            size_limit = config.quotas_channel_quota
        else:
            size_limit = None

    channel = dao.create_channel(new_channel, user_id, authorization.OWNER, size_limit)

    for action in actions:
        task.execute_channel_action(action, channel)


@api_router.patch(
    "/channels/{channel_name}",
    status_code=200,
    tags=["channels"],
    response_model=rest_models.ChannelBase,
)
def patch_channel(
    channel_data: rest_models.Channel,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
    channel: db_models.Channel = Depends(get_channel_or_fail),
    db=Depends(get_db),
):

    auth.assert_update_channel_info(channel.name)

    user_attrs = channel_data.dict(exclude_unset=True)

    if "size_limit" in user_attrs:
        auth.assert_set_channel_size_limit(channel)

    changeable_attrs = ["private", "size_limit"]

    for attr_ in user_attrs.keys():
        if attr_ not in changeable_attrs:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"attribute '{attr_}' of channel can not be changed",
            )

    for attr_, value_ in user_attrs.items():
        setattr(channel, attr_, value_)
    db.commit()

    return channel


@api_router.get(
    "/channels/{channel_name}/packages",
    response_model=List[rest_models.Package],
    tags=["packages"],
)
def get_packages(
    channel: db_models.Channel = Depends(get_channel_or_fail),
    dao: Dao = Depends(get_dao),
    q: Optional[str] = None,
):
    """
    Retrieve all packages in a channel, optionally matching a query `q`.
    """
    return dao.get_packages(channel.name, 0, -1, q)


@api_router.get(
    "/paginated/channels/{channel_name}/packages",
    response_model=rest_models.PaginatedResponse[rest_models.Package],
    tags=["packages"],
)
def get_paginated_packages(
    channel: db_models.Channel = Depends(get_channel_or_fail),
    dao: Dao = Depends(get_dao),
    skip: int = 0,
    limit: int = -1,
    q: Optional[str] = None,
):
    """
    Retrieve all packages in a channel.
    A limit of -1 returns an unpaginated result with all packages. Otherwise, pagination
    is applied.
    """

    return dao.get_packages(channel.name, skip, limit, q)


@api_router.get(
    "/channels/{channel_name}/packages/{package_name}",
    response_model=rest_models.Package,
    tags=["packages"],
)
def get_package(package: db_models.Package = Depends(get_package_or_fail)):
    return package


@api_router.delete(
    "/channels/{channel_name}/packages/{package_name}",
    response_model=rest_models.Package,
    tags=["packages"],
)
def delete_package(
    package: db_models.Package = Depends(get_package_or_fail),
    db=Depends(get_db),
    auth: authorization.Rules = Depends(get_rules),
    dao: Dao = Depends(get_dao),
):

    auth.assert_package_delete(package)

    filenames = [
        os.path.join(version.platform, version.filename)
        for version in package.package_versions  # type: ignore
    ]
    channel_name = package.channel_name

    db.delete(package)
    db.commit()

    for filename in filenames:
        pkgstore.delete_file(channel_name, filename)

    dao.update_channel_size(channel_name)


@api_router.post(
    "/channels/{channel_name}/packages", status_code=201, tags=["packages"]
)
def post_package(
    new_package: rest_models.Package,
    channel: db_models.Channel = Depends(
        ChannelChecker(allow_proxy=False, allow_mirror=False),
    ),
    auth: authorization.Rules = Depends(get_rules),
    dao: Dao = Depends(get_dao),
):

    user_id = auth.assert_user()
    auth.assert_create_package(channel.name)
    pm.hook.validate_new_package(
        channel_name=channel.name,
        package_name=new_package.name,
        file_handler=None,
        condainfo=None,
    )
    package = dao.get_package(channel.name, new_package.name)
    if package:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Package {channel.name}/{new_package.name} exists",
        )

    dao.create_package(channel.name, new_package, user_id, authorization.OWNER)


@api_router.get(
    "/channels/{channel_name}/members",
    response_model=List[rest_models.Member],
    tags=["channels"],
)
def get_channel_members(
    channel: db_models.Channel = Depends(get_channel_or_fail),
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):

    auth.assert_list_channel_members(channel.name)
    member_list = dao.get_channel_members(channel.name)

    return member_list


@api_router.post("/channels/{channel_name}/members", status_code=201, tags=["channels"])
def post_channel_member(
    new_member: rest_models.PostMember,
    channel: db_models.Channel = Depends(get_channel_or_fail),
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):

    auth.assert_add_channel_member(channel.name, new_member.role)

    channel_member = dao.get_channel_member(channel.name, new_member.username)
    if channel_member:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Member {new_member.username} in {channel.name} exists",
        )

    dao.create_channel_member(channel.name, new_member)


@api_router.get(
    "/channels/{channel_name}/packages/{package_name}/members",
    response_model=List[rest_models.Member],
    tags=["packages"],
)
def get_package_members(
    package: db_models.Package = Depends(get_package_or_fail),
    dao: Dao = Depends(get_dao),
):

    member_list = dao.get_package_members(package.channel.name, package.name)

    return member_list


@api_router.post(
    "/channels/{channel_name}/packages/{package_name}/members",
    status_code=201,
    tags=["packages"],
)
def post_package_member(
    new_member: rest_models.PostMember,
    package: db_models.Package = Depends(get_package_or_fail),
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):

    auth.assert_add_package_member(package.channel.name, package.name, new_member.role)

    channel_member = dao.get_package_member(
        package.channel.name, package.name, new_member.username
    )
    if channel_member:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Member {new_member.username} in "
                "{package.channel.name}/{package.name} exists"
            ),
        )

    dao.create_package_member(package.channel.name, package.name, new_member)


@api_router.get(
    "/channels/{channel_name}/packages/{package_name}/versions",
    response_model=List[rest_models.PackageVersion],
    tags=["packages"],
)
def get_package_versions(
    package: db_models.Package = Depends(get_package_or_fail),
    dao: Dao = Depends(get_dao),
    time_created__ge: datetime.datetime = None,
):

    version_profile_list = dao.get_package_versions(package, time_created__ge)
    version_list = []

    for version, profile, api_key_profile in version_profile_list:
        version_data = rest_models.PackageVersion.from_orm(version)
        version_list.append(version_data)

    return version_list


@api_router.get(
    "/channels/{channel_name}/packages/{package_name}/versions/{platform}/{filename}",
    response_model=rest_models.PackageVersion,
    tags=["packages"],
)
def get_package_version(
    platform: str,
    filename: str,
    package_name: str,
    channel_name: str,
    package: db_models.Package = Depends(get_package_or_fail),
    dao: Dao = Depends(get_dao),
):
    version = dao.get_package_version_by_filename(
        channel_name, package_name, filename, platform
    )

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"package version {platform}/{filename} not found",
        )

    return version


@api_router.get(
    "/channels/{channel_name}/packages/{package_name}/versions/{platform}/{filename}/metrics",  # noqa
    response_model=rest_models.PackageVersionMetricSeries,
    tags=["metrics"],
)
def get_package_version_metrics(
    platform: str,
    filename: str,
    package_name: str,
    channel_name: str,
    period: IntervalType = IntervalType.day,
    metric_name: str = "download",
    start: Optional[datetime.datetime] = None,
    end: Optional[datetime.datetime] = None,
    package: db_models.Package = Depends(get_package_or_fail),
    dao: Dao = Depends(get_dao),
):
    version = dao.get_package_version_by_filename(
        channel_name, package_name, filename, platform
    )

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"package version {platform}/{filename} not found",
        )

    series = dao.get_package_version_metrics(
        version.id, period, metric_name, start=start, end=end
    )

    total = sum(s.count for s in series)

    return {
        "period": period,
        "metric_name": metric_name,
        "total": total,
        "series": series,
    }


@api_router.delete(
    "/channels/{channel_name}/packages/{package_name}/versions/{platform}/{filename}",
    response_model=rest_models.PackageVersion,
    tags=["packages"],
)
def delete_package_version(
    platform: str,
    filename: str,
    channel_name: str,
    package_name: str,
    dao: Dao = Depends(get_dao),
    db=Depends(get_db),
    auth: authorization.Rules = Depends(get_rules),
):

    version = dao.get_package_version_by_filename(
        channel_name, package_name, filename, platform
    )

    auth.assert_package_delete(version.package)

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"package version {platform}/{filename} not found",
        )

    db.delete(version)
    db.commit()

    path = os.path.join(platform, filename)
    pkgstore.delete_file(channel_name, path)

    dao.update_channel_size(channel_name)


@api_router.get(
    "/packages/search/", response_model=List[rest_models.PackageSearch], tags=["search"]
)
def search(
    q: str,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    user_id = auth.get_user()
    keywords, filters = parse_query('package', q)
    return dao.search_packages(keywords, filters, user_id)


@api_router.get(
    "/channels/search/", response_model=List[rest_models.ChannelSearch], tags=["search"]
)
def channel_search(
    q: str,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    user_id = auth.get_user()
    keywords, filters = parse_query('channel', q)
    return dao.search_channels(keywords, filters, user_id)


@api_router.get("/api-keys", response_model=List[rest_models.ApiKey], tags=["API keys"])
def get_api_keys(
    dao: Dao = Depends(get_dao), auth: authorization.Rules = Depends(get_rules)
):
    """Get API keys for current user"""

    user_id = auth.assert_user()
    api_key_list = dao.get_api_keys_with_members(user_id)

    from itertools import groupby

    api_keys = []

    grouped_by_key = groupby(api_key_list, key=lambda k: k[0])

    for group_key, group_items in grouped_by_key:
        roles = []
        for _, package_member, channel_member in group_items:
            if package_member:
                roles.append(
                    CPRole(
                        channel=package_member.channel_name,
                        package=package_member.package_name,
                        role=package_member.role,
                    )
                )
            if channel_member:
                roles.append(
                    CPRole(
                        channel=channel_member.channel_name,
                        package=None,
                        role=channel_member.role,
                    )
                )
        api_keys.append(
            rest_models.ApiKey(
                key=group_key.key, description=group_key.description, roles=roles
            )
        )

    return api_keys


@api_router.post(
    "/api-keys", status_code=201, tags=["API keys"], response_model=rest_models.ApiKey
)
def post_api_key(
    api_key: rest_models.BaseApiKey,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):

    auth.assert_create_api_key_roles(api_key.roles)

    user_id = auth.assert_user()

    key = generate_random_key(32)
    dao.create_api_key(user_id, api_key, key)

    return rest_models.ApiKey(
        description=api_key.description, roles=api_key.roles, key=key
    )


@api_router.delete("/api-keys/{key}", tags=["API keys"])
def delete_api_keys(
    key: str,
    dao: Dao = Depends(get_dao),
    db: Session = Depends(get_db),
    auth: authorization.Rules = Depends(get_rules),
):
    api_key = dao.get_api_key(key)

    if not api_key:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"key '{key}' does not exist"
        )

    auth.assert_delete_api_key(api_key)

    api_key.deleted = True

    db.commit()


@api_router.post(
    "/channels/{channel_name}/packages/{package_name}/files/",
    status_code=201,
    tags=["files"],
)
def post_file_to_package(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    force: Optional[bool] = Form(None),
    package: db_models.Package = Depends(get_package_or_fail),
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
    channel: db_models.Channel = Depends(
        ChannelChecker(allow_proxy=False, allow_mirror=False),
    ),
):
    handle_package_files(package.channel.name, files, dao, auth, force, package=package)
    dao.update_channel_size(package.channel_name)


@api_router.post("/channels/{channel_name}/files/", status_code=201, tags=["files"])
def post_file_to_channel(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    force: Optional[bool] = Form(None),
    channel: db_models.Channel = Depends(
        ChannelChecker(allow_proxy=False, allow_mirror=False)
    ),
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    handle_package_files(channel.name, files, dao, auth, force)

    dao.update_channel_size(channel.name)

    # Background task to update indexes
    background_tasks.add_task(indexing.update_indexes, dao, pkgstore, channel.name)


@retry(
    stop=stop_after_attempt(3),
    retry=(retry_if_result(lambda x: x is None)),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    after=after_log(logger, logging.WARNING),
)
def _extract_and_upload_package(file, channel_name):
    try:
        conda_info = CondaInfo(file.file, file.filename)
    except Exception as e:
        logger.error(
            f"Could not extract conda-info from package {file.filename}\n{str(e)}"
        )
        raise e

    dest = os.path.join(conda_info.info["subdir"], file.filename)
    parts = file.filename.rsplit("-", 2)

    if parts[0] != conda_info.info["name"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"package file name and info files do not match {file.filename}",
        )

    try:
        file.file.seek(0)
        logger.debug(
            f"uploading file {dest} from channel {channel_name} to package store"
        )
        pkgstore.add_package(file.file, channel_name, dest)
    except AttributeError as e:
        logger.error(f"Could not upload {file}, {file.filename}. {str(e)}")
        return None

    return conda_info


def handle_package_files(
    channel_name,
    files,
    dao,
    auth,
    force,
    package=None,
):
    user_id = auth.assert_user()

    # quick fail if not allowed to upload
    # note: we're checking later that `parts[0] == conda_info.package_name`
    total_size = 0
    for file in files:
        parts = file.filename.rsplit("-", 2)
        if len(parts) != 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"package file name has wrong format {file.filename}",
            )
        else:
            package_name = parts[0]
        auth.assert_upload_file(channel_name, package_name)
        if force:
            auth.assert_overwrite_package_version(channel_name, package_name)

        # workaround for https://github.com/python/cpython/pull/3249
        if type(file.file) is SpooledTemporaryFile and not hasattr(file, "seekable"):
            file.file.seekable = file.file._file.seekable

        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        total_size += size
        file.file.seek(0)

    dao.assert_size_limits(channel_name, total_size)

    with TicToc("extract conda-info and upload file"):
        pkgstore.create_channel(channel_name)
        nthreads = config.general_package_unpack_threads
        with ThreadPoolExecutor(max_workers=nthreads) as executor:
            try:
                conda_infos = [
                    ci
                    for ci in executor.map(
                        _extract_and_upload_package, files, (channel_name,) * len(files)
                    )
                ]
            except exceptions.PackageError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail
                )
    conda_infos = [ci for ci in conda_infos if ci is not None]

    for file, condainfo in zip(files, conda_infos):
        logger.debug(f"Handling {condainfo.info['name']} -> {file.filename}")

        package_name = condainfo.info["name"]
        parts = file.filename.rsplit("-", 2)

        # check that the filename matches the package name
        # TODO also validate version and build string
        if parts[0] != condainfo.info["name"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="filename does not match package name",
            )
        if package and (parts[0] != package.name or package_name != package.name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"requested package endpoint '{package.name}'"
                    f"does not match the uploaded package name '{parts[0]}'"
                ),
            )

        def _delete_file(condainfo, filename):
            dest = os.path.join(condainfo.info["subdir"], file.filename)
            pkgstore.delete_file(channel_name, dest)

        if not package and not dao.get_package(channel_name, package_name):

            try:
                pm.hook.validate_new_package(
                    channel_name=channel_name,
                    package_name=package_name,
                    file_handler=file.file,
                    condainfo=condainfo,
                )
                # validate uploaded package size and existence
                try:
                    pkgsize, _, _ = pkgstore.get_filemetadata(
                        channel_name, f"{condainfo.info['subdir']}/{file.filename}"
                    )
                    if pkgsize != condainfo.info['size']:
                        raise errors.ValidationError(
                            f"Uploaded package {file.filename} "
                            "file size is wrong! Deleting"
                        )
                except FileNotFoundError:
                    raise errors.ValidationError(
                        f"Uploaded package {file.filename} "
                        "file did not upload correctly!"
                    )

                package_data = rest_models.Package(
                    name=package_name,
                    summary=str(condainfo.about.get("summary", "n/a")),
                    description=str(condainfo.about.get("description", "n/a")),
                )
            except pydantic.main.ValidationError as err:
                _delete_file(condainfo, file.filename)
                raise errors.ValidationError(
                    "Validation Error for package: "
                    + f"{channel_name}/{file.filename}: {str(err)}"
                )
            except errors.ValidationError as err:
                _delete_file(condainfo, file.filename)
                logger.error(
                    f"Validation error in: {channel_name}/{file.filename}: {str(err)}"
                )
                raise err

            dao.create_package(
                channel_name,
                package_data,
                user_id,
                authorization.OWNER,
            )

        # Update channeldata info
        dao.update_package_channeldata(
            channel_name, package_name, condainfo.channeldata
        )

        try:
            version = dao.create_version(
                channel_name=channel_name,
                package_name=package_name,
                package_format=condainfo.package_format,
                platform=condainfo.info["subdir"],
                version=condainfo.info["version"],
                build_number=condainfo.info["build_number"],
                build_string=condainfo.info["build"],
                size=condainfo.info["size"],
                filename=file.filename,
                info=json.dumps(condainfo.info),
                uploader_id=user_id,
                upsert=force,
            )
        except IntegrityError:
            logger.error(
                f"duplicate package '{package_name}' in channel '{channel_name}'"
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Duplicate"
            )

        pm.hook.post_add_package_version(version=version, condainfo=condainfo)


app.include_router(
    api_router,
    prefix="/api",
)


@app.get("/api/.*", status_code=404, include_in_schema=False)
def invalid_api():
    return None


@app.get("/channels/{channel_name}/{path:path}")
async def serve_path(
    path,
    channel: db_models.Channel = Depends(get_channel_allow_proxy),
    accept_encoding: Optional[str] = Header(None),
    cache: LocalCache = Depends(LocalCache),
    session=Depends(get_remote_session),
    dao: Dao = Depends(get_dao),
):
    if channel.mirror_channel_url and channel.mirror_mode == "proxy":
        repository = RemoteRepository(channel.mirror_channel_url, session)
        return get_from_cache_or_download(repository, cache, path)

    chunk_size = 10_000

    if pkgstore_support_url and (path.endswith('.tar.bz2') or path.endswith('.conda')):
        # we have to ignore type checking here right now, sorry
        return RedirectResponse(pkgstore.url(channel.name, path))  # type: ignore

    if path.endswith(".tar.bz2") or path.endswith(".conda"):
        try:
            platform, filename = os.path.split(path)
            dao.incr_download_count(channel.name, filename, platform)
        except ValueError:
            pass

    def iter_chunks(fid):
        while True:
            data = fid.read(chunk_size)
            if not data:
                break
            yield data

    if path == "" or path.endswith("/"):
        path += "index.html"
    package_content_iter = None

    headers = {}
    if accept_encoding and 'gzip' in accept_encoding and path.endswith('.json'):
        # return gzipped response
        try:
            package_content_iter = iter_chunks(
                pkgstore.serve_path(channel.name, path + '.gz')
            )
            path += '.gz'
            headers['Content-Encoding'] = 'gzip'
            headers['Content-Type'] = 'application/json'
        except FileNotFoundError:
            pass

    while not package_content_iter:
        try:
            package_content_iter = iter_chunks(pkgstore.serve_path(channel.name, path))

        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{channel.name}/{path} not found",
            )
        except IsADirectoryError:
            path += "/index.html"

    fsize, fmtime, fetag = pkgstore.get_filemetadata(channel.name, path)
    headers.update(
        {
            'Cache-Control': 'max-age=' + str(60 * 60 * 10),  # 10 hours
            'Content-Size': str(fsize),
            'Last-Modified': formatdate(fmtime, usegmt=True),
            'ETag': fetag,
        }
    )
    logger.debug(f"File response headers: {headers}")
    return StreamingResponse(package_content_iter, headers=headers)


frontend.register(app)
