# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.
import asyncio
import datetime
import json
import logging
import os
import re
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from email.utils import formatdate
from tempfile import SpooledTemporaryFile
from typing import List, Optional, Tuple, Type

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
from fastapi.responses import RedirectResponse, StreamingResponse
from importlib_metadata import entry_points
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.sessions import SessionMiddleware
from tenacity import (
    after_log,
    retry,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

from quetz import (
    authorization,
    db_models,
    errors,
    exceptions,
    frontend,
    metrics,
    rest_models,
)
from quetz.authentication import AuthenticatorRegistry, BaseAuthenticator
from quetz.authentication import github as auth_github
from quetz.authentication import gitlab as auth_gitlab
from quetz.authentication import google as auth_google
from quetz.authentication.azuread import AzureADAuthenticator
from quetz.authentication.jupyterhub import JupyterhubAuthenticator
from quetz.authentication.pam import PAMAuthenticator
from quetz.config import PAGINATION_LIMIT, Config, configure_logger, get_plugin_manager
from quetz.dao import Dao
from quetz.deps import (
    ChannelChecker,
    get_channel_allow_proxy,
    get_channel_or_fail,
    get_config,
    get_dao,
    get_db,
    get_package_or_fail,
    get_remote_session,
    get_rules,
    get_session,
    get_tasks_worker,
)
from quetz.jobs import api as jobs_api
from quetz.jobs import rest_models as jobs_rest
from quetz.metrics import api as metrics_api
from quetz.metrics.middleware import DOWNLOAD_COUNT, UPLOAD_COUNT
from quetz.rest_models import ChannelActionEnum, CPRole
from quetz.tasks import indexing
from quetz.tasks.common import Task
from quetz.tasks.mirror import RemoteRepository, download_remote_file
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

if config.general_redirect_http_to_https:
    logger.info("Configuring http to https redirect ")
    app.add_middleware(HTTPSRedirectMiddleware)

metrics.init(app)

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

# global variables for batching download counts

download_counts: Counter = Counter()

DOWNLOAD_INCREMENT_DELAY_SECONDS = 10
DOWNLOAD_INCREMENT_MAX_DOWNLOADS = 50


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


app.add_middleware(CondaTokenMiddleware)

pkgstore = config.get_package_store()

# authenticators


builtin_authenticators: List[Type[BaseAuthenticator]] = [
    authenticator
    for authenticator in [
        auth_github.GithubAuthenticator,
        auth_gitlab.GitlabAuthenticator,
        auth_google.GoogleAuthenticator,
        JupyterhubAuthenticator,
        PAMAuthenticator,
        AzureADAuthenticator,
    ]
    if authenticator is not None
]

plugin_authenticators: List[Type[BaseAuthenticator]] = [
    ep.load() for ep in entry_points().select(group='quetz.authenticator')
]


auth_registry = AuthenticatorRegistry()
auth_registry.set_router(app)

for auth_cls in builtin_authenticators + plugin_authenticators:
    auth_obj = auth_cls(config)
    if auth_obj.is_enabled:
        auth_registry.register(auth_obj)

# other routers

pm = get_plugin_manager()
api_router = APIRouter()
plugin_routers = pm.hook.register_router()

for router in plugin_routers:
    app.include_router(router)
app.include_router(jobs_api.get_router())
app.include_router(metrics_api.get_router())


# helper functions
async def check_token_revocation(session):
    valid = True
    identity_provider = session.get("identity_provider")

    if identity_provider is None:
        valid = False
    elif identity_provider != "dummy":
        auth_obj = auth_registry.enabled_authenticators[identity_provider]
        valid = await auth_obj.validate_token(session.get("token"))
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
    if profile:
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
    limit: int = PAGINATION_LIMIT,
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


@api_router.get(
    "/users/{username}/channels",
    response_model=List[rest_models.ChannelRole],
    tags=["users"],
)
def get_user_channels(
    username: str,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    return list_user_channels(username, dao, auth, 0, -1)


@api_router.get(
    "/users/{username}/packages",
    response_model=List[rest_models.PackageRole],
    tags=["users"],
)
def get_user_packages(
    username: str,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):

    return list_user_packages(username, dao, auth, 0, -1)


@api_router.get(
    "/paginated/users/{username}/channels",
    response_model=rest_models.PaginatedResponse[rest_models.ChannelRole],
    tags=["users"],
)
def get_paginated_user_channels(
    username: str,
    skip: int = 0,
    limit: int = PAGINATION_LIMIT,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    return list_user_channels(username, dao, auth, skip, limit)


@api_router.get(
    "/paginated/users/{username}/packages",
    response_model=rest_models.PaginatedResponse[rest_models.PackageRole],
    tags=["users"],
)
def get_paginated_user_packages(
    username: str,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
    skip: int = 0,
    limit: int = PAGINATION_LIMIT,
):
    return list_user_packages(username, dao, auth, skip, limit)


def list_user_packages(
    username: str,
    dao: Dao,
    auth: authorization.Rules,
    skip: int,
    limit: int,
):
    user = dao.get_user_by_username(username)

    if not user or not user.profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User {username} not found"
        )

    auth.assert_read_user_data(user.id)

    return dao.get_user_packages(skip, limit, user.id)


def list_user_channels(
    username: str, dao: Dao, auth: authorization.Rules, skip: int, limit: int
):
    user = dao.get_user_by_username(username)

    if not user or not user.profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User {username} not found"
        )

    auth.assert_read_user_data(user.id)

    channels = dao.get_user_channels_with_role(skip, limit, user.id)

    return channels


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
    "/channels", response_model=List[rest_models.ChannelExtra], tags=["channels"]
)
def get_channels(
    public: bool = True,
    dao: Dao = Depends(get_dao),
    q: str = None,
    auth: authorization.Rules = Depends(get_rules),
):
    """List all channels"""

    user_id = auth.get_user()
    return dao.get_channels(0, -1, q, user_id, include_public=public)


@api_router.get(
    "/paginated/channels",
    response_model=rest_models.PaginatedResponse[rest_models.ChannelExtra],
    tags=["channels"],
)
def get_paginated_channels(
    dao: Dao = Depends(get_dao),
    skip: int = 0,
    limit: int = PAGINATION_LIMIT,
    public: bool = True,
    q: str = None,
    auth: authorization.Rules = Depends(get_rules),
):
    """List all channels, as a paginated response"""
    user_id = auth.get_user()
    return dao.get_channels(skip, limit, q, user_id, include_public=public)


@api_router.get(
    "/channels/{channel_name}",
    response_model=rest_models.ChannelExtra,
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
    request: Request,
    mirror: rest_models.ChannelMirrorBase,
    channel_name: str,
    channel: db_models.Channel = Depends(get_channel_or_fail),
    auth: authorization.Rules = Depends(get_rules),
    dao: Dao = Depends(get_dao),
    remote_session: requests.Session = Depends(get_remote_session),
):

    auth.assert_register_mirror(channel_name)

    logger.debug(f"registering mirror {mirror.url}")

    if not mirror.api_endpoint:
        mirror.api_endpoint = mirror.url.replace("get", "api/channels")

    if not mirror.metrics_endpoint:
        mirror.metrics_endpoint = mirror.url.replace("get", "metrics/channels")

    # check api response
    response = remote_session.get(mirror.api_endpoint)

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"could not connect to remote repository {mirror.url}",
        )
    response_data = response.json()

    try:
        mirrored_server = response_data["mirror_channel_url"]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="mirror server is not quetz server",
        )

    if not mirrored_server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{mirror.url} is not a mirror server",
        )

    dao.create_channel_mirror(
        channel_name, mirror.url, mirror.api_endpoint, mirror.metrics_endpoint
    )

    logger.info(f"successfully registered mirror {mirror.url}")


@api_router.get(
    "/channels/{channel_name}/mirrors",
    response_model=List[rest_models.ChannelMirror],
    tags=["channels"],
)
def get_channel_mirrors(
    channel_name: str,
    channel: db_models.Channel = Depends(get_channel_or_fail),
    auth: authorization.Rules = Depends(get_rules),
    dao: Dao = Depends(get_dao),
):
    return channel.mirrors


@api_router.delete(
    "/channels/{channel_name}/mirrors/{mirror_id}",
    response_model=List[rest_models.ChannelMirror],
    tags=["channels"],
)
def delete_channel_mirror(
    channel_name: str,
    mirror_id: str,
    channel: db_models.Channel = Depends(get_channel_or_fail),
    auth: authorization.Rules = Depends(get_rules),
    dao: Dao = Depends(get_dao),
):
    auth.assert_unregister_mirror(channel_name)
    dao.delete_channel_mirror(channel_name, mirror_id)


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
    try:
        pkgstore.remove_channel(channel.name)
    except FileNotFoundError:
        logger.warning(
            f"trying to remove non-existent package store for channel {channel.name}"
        )


@api_router.put(
    "/channels/{channel_name}/actions", tags=["channels"], response_model=jobs_rest.Job
)
def put_mirror_channel_actions(
    action: rest_models.ChannelAction,
    channel: db_models.Channel = Depends(get_channel_allow_proxy),
    dao: Dao = Depends(get_dao),
    task: Task = Depends(get_tasks_worker),
):

    new_job = task.execute_channel_action(
        action.action,
        channel,
        start_at=action.start_at,
        repeat_every_seconds=action.repeat_every_seconds,
    )
    return new_job


@api_router.post("/channels", status_code=201, tags=["channels"])
def post_channel(
    request: Request,
    new_channel: rest_models.Channel,
    background_tasks: BackgroundTasks,
    mirror_api_key: Optional[str] = None,
    register_mirror: bool = False,
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
    task: Task = Depends(get_tasks_worker),
    config=Depends(get_config),
    session: requests.Session = Depends(get_remote_session),
):

    user_id = auth.assert_user()

    existing_channel = dao.get_channel(new_channel.name)

    if existing_channel:
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

    if new_channel.actions is None:
        if is_mirror:
            actions = [ChannelActionEnum.synchronize_repodata]
        else:
            actions = []
    else:
        actions = new_channel.actions

    includelist = new_channel.metadata.includelist
    excludelist = new_channel.metadata.excludelist

    if includelist is not None and excludelist is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot use both `includelist` and `excludelist` together.",
        )

    user_attrs = new_channel.dict(exclude_unset=True)

    if "size_limit" in user_attrs:
        auth.assert_set_channel_size_limit()
        size_limit = new_channel.size_limit
    else:
        if config.configured_section("quotas"):
            size_limit = config.quotas_channel_quota
        else:
            size_limit = None

    channel = dao.create_channel(new_channel, user_id, authorization.OWNER, size_limit)
    pkgstore.create_channel(new_channel.name)
    indexing.update_indexes(dao, pkgstore, new_channel.name)

    # register mirror
    if is_mirror and register_mirror:
        mirror_url = str(new_channel.mirror_channel_url)
        mirror_url = mirror_url.replace("get", "api/channels")
        headers = {"x-api-key": mirror_api_key} if mirror_api_key else {}
        api_endpoint = str(request.url.replace(query=None)) + '/' + new_channel.name
        request.url
        response = session.post(
            mirror_url + '/mirrors',
            json={
                "url": api_endpoint.replace("api/channels", "get"),
                "api_endpoint": api_endpoint,
                "metrics_endpoint": api_endpoint.replace("api", "metrics"),
            },
            headers=headers,
        )
        if response.status_code != 201:
            logger.warning(f"could not register mirror due to error {response.text}")

    for action in actions:
        task.execute_channel_action(
            action,
            channel,
        )


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
        auth.assert_set_channel_size_limit()

    changeable_attrs = ["private", "size_limit", "metadata", "ttl"]

    for attr_ in user_attrs.keys():
        if attr_ not in changeable_attrs:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"attribute '{attr_}' of channel can not be changed",
            )

    for attr_, value_ in user_attrs.items():
        if attr_ == "metadata":
            metadata = channel.load_channel_metadata()
            metadata.update(value_)
            setattr(channel, "channel_metadata", json.dumps(metadata))
        else:
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
    res = dao.get_packages(channel.name, 0, -1, q)
    return res


@api_router.get(
    "/paginated/channels/{channel_name}/packages",
    response_model=rest_models.PaginatedResponse[rest_models.Package],
    tags=["packages"],
)
def get_paginated_packages(
    channel: db_models.Channel = Depends(get_channel_or_fail),
    dao: Dao = Depends(get_dao),
    skip: int = 0,
    limit: int = PAGINATION_LIMIT,
    q: Optional[str] = None,
    order_by: Optional[str] = None,
):
    """
    Retrieve all packages in a channel.
    A limit of -1 returns an unpaginated result with all packages. Otherwise, pagination
    is applied.
    """

    return dao.get_packages(channel.name, skip, limit, q, order_by)


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
    db=Depends(get_db),
    auth: authorization.Rules = Depends(get_rules),
):

    if not dao.get_user_by_username(new_member.username):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"user {new_member.username} not found",
        )

    auth.assert_list_channel_members(channel.name)
    channel_member = dao.get_channel_member(channel.name, new_member.username)

    auth.assert_add_channel_member(channel.name, new_member.role)

    if channel_member:
        channel_member.role = new_member.role
        db.commit()
    else:
        dao.create_channel_member(channel.name, new_member)


@api_router.delete("/channels/{channel_name}/members", tags=["channels"])
def delete_channel_member(
    username: str,
    channel: db_models.Channel = Depends(get_channel_or_fail),
    dao: Dao = Depends(get_dao),
    db=Depends(get_db),
    auth: authorization.Rules = Depends(get_rules),
):

    if not dao.get_user_by_username(username):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"user {username} not found",
        )

    auth.assert_list_channel_members(channel.name)
    channel_member = dao.get_channel_member(channel.name, username)

    if not channel_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"user {username} is not a member of channel {channel.name}",
        )

    auth.assert_remove_channel_member(channel.name, channel_member.role)

    db.delete(channel_member)
    db.commit()


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
    version_match_str: str = None,
):

    version_profile_list = dao.get_package_versions(
        package, time_created__ge, version_match_str
    )
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
    user_role_keys, custom_role_keys = dao.get_api_keys_with_members(user_id)

    api_keys = []

    for key in user_role_keys:
        api_keys.append(
            rest_models.ApiKey(
                key=key.key,
                description=key.description,
                time_created=key.time_created,
                expire_at=key.expire_at,
                roles=None,
            )
        )

    from itertools import groupby

    grouped_by_key = groupby(custom_role_keys, key=lambda k: k[0])

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
                key=group_key.key,
                description=group_key.description,
                time_created=group_key.time_created,
                expire_at=group_key.expire_at,
                roles=roles,
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

    user_role_keys, custom_role_keys = dao.get_api_keys_with_members(user_id, key)

    if len(user_role_keys) > 0:
        key = user_role_keys[0]
        return rest_models.ApiKey(
            key=key.key,
            description=key.description,
            time_created=key.time_created,
            expire_at=key.expire_at,
            roles=None,
        )

    else:
        key = custom_role_keys[0][0]
        package_member = custom_role_keys[0][1]
        channel_member = custom_role_keys[0][2]
        roles = []
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

        return rest_models.ApiKey(
            key=key.key,
            description=key.description,
            time_created=key.time_created,
            expire_at=key.expire_at,
            roles=roles,
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
    handle_package_files(package.channel, files, dao, auth, force, package=package)
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
    handle_package_files(channel, files, dao, auth, force)

    dao.update_channel_size(channel.name)

    # Background task to update indexes
    background_tasks.add_task(indexing.update_indexes, dao, pkgstore, channel.name)


@retry(
    stop=stop_after_attempt(3),
    retry=(retry_if_result(lambda x: x is None)),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    after=after_log(logger, logging.WARNING),
)
def _extract_and_upload_package(file, channel_name, channel_proxylist):
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

    if channel_proxylist and conda_info.info["name"] in channel_proxylist:
        # do not upload files that are proxied
        logger.info(f"Skip upload of proxied file {file.filename}")
        return conda_info

    try:
        file.file.seek(0)
        logger.debug(
            f"Uploading file {dest} from channel {channel_name} to package store"
        )
        pkgstore.add_package(file.file, channel_name, dest)
    except AttributeError as e:
        logger.error(f"Could not upload {file}, {file.filename}. {str(e)}")
        return None

    return conda_info


def handle_package_files(
    channel,
    files,
    dao,
    auth,
    force,
    package=None,
    is_mirror_op=False,
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
        auth.assert_upload_file(channel.name, package_name)
        if force:
            auth.assert_overwrite_package_version(channel.name, package_name)

        # workaround for https://github.com/python/cpython/pull/3249
        if type(file.file) is SpooledTemporaryFile and not hasattr(file, "seekable"):
            file.file.seekable = file.file._file.seekable

        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        total_size += size
        file.file.seek(0)

    dao.assert_size_limits(channel.name, total_size)

    channel_proxylist = []
    if channel.mirror_mode:
        if not is_mirror_op:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot upload packages to mirror channel",
            )
        else:
            channel_proxylist = json.loads(channel.channel_metadata).get(
                'proxylist', []
            )

    pkgstore.create_channel(channel.name)
    nthreads = config.general_package_unpack_threads
    with ThreadPoolExecutor(max_workers=nthreads) as executor:
        try:
            conda_infos = [
                ci
                for ci in executor.map(
                    _extract_and_upload_package,
                    files,
                    (channel.name,) * len(files),
                    (channel_proxylist,) * len(files),
                )
            ]
        except exceptions.PackageError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail
            )

    conda_infos = [ci for ci in conda_infos if ci is not None]

    for file, condainfo in zip(files, conda_infos):
        logger.debug(f"Handling {condainfo.info['name']} -> {file.filename}")
        package_type = "tar.bz2" if file.filename.endswith(".tar.bz2") else "conda"
        UPLOAD_COUNT.labels(
            channel=channel.name,
            platform=condainfo.info["subdir"],
            package_name=condainfo.info["name"],
            version=condainfo.info["version"],
            package_type=package_type,
        ).inc()

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
            pkgstore.delete_file(channel.name, dest)

        if not package and not dao.get_package(channel.name, package_name):

            try:
                if not channel_proxylist or package_name not in channel_proxylist:
                    pm.hook.validate_new_package(
                        channel_name=channel.name,
                        package_name=package_name,
                        file_handler=file.file,
                        condainfo=condainfo,
                    )
                    # validate uploaded package size and existence
                    try:
                        pkgsize, _, _ = pkgstore.get_filemetadata(
                            channel.name, f"{condainfo.info['subdir']}/{file.filename}"
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
                    + f"{channel.name}/{file.filename}: {str(err)}"
                )
            except errors.ValidationError as err:
                _delete_file(condainfo, file.filename)
                logger.error(
                    f"Validation error in: {channel.name}/{file.filename}: {str(err)}"
                )
                raise err

            dao.create_package(
                channel.name,
                package_data,
                user_id,
                authorization.OWNER,
            )

        # Update channeldata info
        dao.update_package_channeldata(
            channel.name, package_name, condainfo.channeldata
        )

        try:
            version = dao.create_version(
                channel_name=channel.name,
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
                f"duplicate package '{package_name}' in channel '{channel.name}'"
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


@app.on_event("startup")
def start_sync_download_counts():

    global download_counts
    wait_time = 1  # seconds

    db_manager = contextmanager(get_db)

    def commit_to_db(counts):
        count: int
        package = Tuple[str, str, str]

        with TicToc("sync download counts"):
            with db_manager(config) as db:
                dao = get_dao(db)
                for package, count in counts.items():
                    dao.incr_download_count(*package, incr=count)

    async def task():
        last_download_sync = None
        increment_delay = datetime.timedelta(seconds=DOWNLOAD_INCREMENT_DELAY_SECONDS)
        try:
            while True:
                n_total_downloads = sum(download_counts.values())
                now = datetime.datetime.utcnow()
                if n_total_downloads < DOWNLOAD_INCREMENT_MAX_DOWNLOADS:
                    if not n_total_downloads or (
                        last_download_sync
                        and (last_download_sync + increment_delay) > now
                    ):
                        await asyncio.sleep(wait_time)
                        continue
                logger.debug(
                    "Download counts: time since last sync %s, n/o downloads: %s",
                    now - (last_download_sync or now),
                    n_total_downloads,
                )
                new_items = download_counts.copy()
                download_counts.clear()
                await run_in_threadpool(commit_to_db, new_items)
                last_download_sync = now
        except asyncio.CancelledError:
            commit_to_db(download_counts)
            download_counts.clear()
            raise

    app.sync_download_task = asyncio.create_task(task())


@app.on_event("shutdown")
async def stop_sync_donwload_counts():
    app.sync_download_task.cancel()
    try:
        await app.sync_download_task
    except asyncio.CancelledError:
        pass


@app.head("/get/{channel_name}/{path:path}")
@app.get("/get/{channel_name}/{path:path}")
def serve_path(
    path,
    channel: db_models.Channel = Depends(get_channel_allow_proxy),
    accept_encoding: Optional[str] = Header(None),
    session=Depends(get_remote_session),
    dao: Dao = Depends(get_dao),
):

    chunk_size = 10_000

    is_package_request = path.endswith((".tar.bz2", ".conda"))

    package_name = None
    if is_package_request:
        try:
            platform, filename = os.path.split(path)
            package_name, version, hash_end = filename.rsplit('-', 2)
            package_type = "tar.bz2" if hash_end.endswith(".tar.bz2") else "conda"
            DOWNLOAD_COUNT.labels(
                channel=channel.name,
                platform=platform,
                package_name=package_name,
                version=version,
                package_type=package_type,
            ).inc()
            download_counts[(channel.name, filename, platform)] += 1
        except ValueError:
            pass

    if is_package_request and channel.mirror_channel_url:
        # if we exclude the package from syncing, redirect to original URL
        channel_proxylist = json.loads(channel.channel_metadata).get('proxylist', [])
        if channel_proxylist and package_name and package_name in channel_proxylist:
            return RedirectResponse(f"{channel.mirror_channel_url}/{path}")

    if channel.mirror_channel_url and channel.mirror_mode == "proxy":
        repository = RemoteRepository(channel.mirror_channel_url, session)
        if not pkgstore.file_exists(channel.name, path):
            download_remote_file(repository, pkgstore, channel.name, path)
        elif path.endswith(".json"):
            # repodata.json and current_repodata.json are cached locally
            # for channel.ttl seconds
            _, fmtime, _ = pkgstore.get_filemetadata(channel.name, path)
            if time.time() - fmtime >= channel.ttl:
                download_remote_file(repository, pkgstore, channel.name, path)

    if (
        is_package_request or pkgstore.kind == "LocalStore"
    ) and pkgstore.support_redirect:
        return RedirectResponse(pkgstore.url(channel.name, path))

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
            'Cache-Control': f'max-age={channel.ttl}',
            'Content-Size': str(fsize),
            'Last-Modified': formatdate(fmtime, usegmt=True),
            'ETag': fetag,
        }
    )
    return StreamingResponse(package_content_iter, headers=headers)


@app.get("/get/{channel_name}")
def serve_channel_index(
    channel: db_models.Channel = Depends(get_channel_allow_proxy),
    accept_encoding: Optional[str] = Header(None),
    session=Depends(get_remote_session),
    dao: Dao = Depends(get_dao),
):
    return serve_path("index.html", channel, accept_encoding, session, dao)


frontend.register(app)
