# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field, root_validator, validator
from pydantic.generics import GenericModel

T = TypeVar('T')


class BaseProfile(BaseModel):
    name: Optional[str]
    avatar_url: str

    class Config:
        orm_mode = True


class Profile(BaseProfile):
    user: BaseUser


class BaseUser(BaseModel):
    id: uuid.UUID
    username: str

    class Config:
        orm_mode = True


class User(BaseUser):
    profile: BaseProfile


Profile.update_forward_refs()


Role = Field(None, regex='owner|maintainer|member')


class Member(BaseModel):
    role: str = Role
    user: User

    class Config:
        orm_mode = True


class Pagination(BaseModel):
    skip: int = Field(0, title='The number of skipped records')
    limit: int = Field(0, title='The maximum number of returned records')
    all_records_count: int = Field(0, title="The number of available records")


class MirrorMode(str, Enum):
    proxy = "proxy"
    mirror = "mirror"


class ChannelBase(BaseModel):

    name: str = Field(None, title='The name of the channel', max_length=50)
    description: str = Field(
        None, title='The description of the channel', max_length=300
    )
    private: bool = Field(True, title="channel should be private")
    size_limit: Optional[int] = Field(None, title="size limit of the channel")
    ttl: int = Field(36000, title="ttl of the channel")
    mirror_channel_url: Optional[str] = Field(None, regex="^(http|https)://.+")
    mirror_mode: Optional[MirrorMode] = None

    @validator("size_limit")
    def check_positive(cls, v):
        if v is not None and v < 0:
            return ValueError("must be positive value")
        return v

    class Config:
        orm_mode = True


class ChannelExtra(ChannelBase):
    members_count: int
    packages_count: int


class ChannelRole(BaseModel):
    name: str = Field(title="channel name")
    role: str = Field(title="user role")

    class Config:
        orm_mode = True


class ChannelActionEnum(str, Enum):
    """Execute special actions on channels (they may need specific permissions):

    * `synchronize` -- _mirror only_, synchronize mirror channels and extract metadata
      from packages (compute heavy)
    * `synchronize_repodata` -- _mirror only_, synchronize mirror channels by extracting
      metadata from index (less heavy)
    * `reindex` -- find all downloaded packages and re-create db and index
    * `generate_indexes` -- generate indexes (repodata.json and other) from data in db
    * `validate_packages` -- validate package files
    * `synchronize_metrics` -- _non-mirror_, pull download metrics from known mirrors
    * `cleanup` -- fix inconsistencies in database and pkgstore
    * `cleanup_dry_run` -- display what changes `cleanup` would do
    """

    synchronize = 'synchronize'
    synchronize_repodata = "synchronize_repodata"
    reindex = 'reindex'
    generate_indexes = 'generate_indexes'
    validate_packages = 'validate_packages'
    synchronize_metrics = 'synchronize_metrics'
    cleanup = 'cleanup'
    cleanup_dry_run = 'cleanup_dry_run'

    # handlers for new actions should be registered in quetz.job.handlers


class ChannelMetadata(BaseModel):

    includelist: Optional[List[str]] = Field(
        None, title="list of packages to include while creating a channel"
    )
    excludelist: Optional[List[str]] = Field(
        None, title="list of packages to exclude while creating a channel"
    )
    proxylist: Optional[List[str]] = Field(
        None,
        title="list of packages that should only be proxied (not copied, "
        "stored and redistributed)",
    )


class Channel(ChannelBase):

    metadata: ChannelMetadata = Field(
        default_factory=ChannelMetadata, title="channel metadata", example={}
    )

    actions: Optional[List[ChannelActionEnum]] = Field(
        None,
        title="list of actions to run after channel creation "
        "(see /channels/{}/actions for description)",
    )

    @root_validator
    def check_mirror_params(cls, values):
        mirror_url = values.get("mirror_channel_url")
        mirror_mode = values.get("mirror_mode")

        if mirror_url and not mirror_mode:
            raise ValueError(
                "'mirror_channel_url' provided but 'mirror_mode' is undefined"
            )
        if not mirror_url and mirror_mode:
            raise ValueError(
                "'mirror_mode' provided but 'mirror_channel_url' is undefined"
            )

        return values


class ChannelMirrorBase(BaseModel):
    url: str = Field(None, regex="^(http|https)://.+")
    api_endpoint: Optional[str] = Field(None, regex="^(http|https)://.+")
    metrics_endpoint: Optional[str] = Field(None, regex="^(http|https)://.+")

    class Config:
        orm_mode = True


class ChannelMirror(ChannelMirrorBase):
    id: uuid.UUID


class Package(BaseModel):
    name: str = Field(
        None, title='The name of package', max_length=1500, regex=r'^[a-z0-9-_\.]*$'
    )
    summary: str = Field(None, title='The summary of the package')
    description: str = Field(None, title='The description of the package')
    url: str = Field(None, title="project url")
    platforms: List[str] = Field(None, title="supported platforms")
    current_version: str = Field(None, title="latest version of any platform")
    latest_change: datetime = Field(None, title="date of latest change")

    @validator("platforms", pre=True)
    def parse_list_of_platforms(cls, v):

        if isinstance(v, str):
            return v.split(":")
        else:
            return v

    class Config:
        orm_mode = True


class PackageRole(BaseModel):
    name: str = Field(title='The name of package')
    channel_name: str = Field(title='The channel this package belongs to')
    role: str = Field(title="user role for this package")

    class Config:
        orm_mode = True


class PackageSearch(Package):
    channel_name: str = Field(None, title='The channel this package belongs to')


class ChannelSearch(BaseModel):
    name: str = Field(None, title='The name of the channel', max_length=1500)
    description: str = Field(None, title='The description of the channel')
    private: bool = Field(None, title='The visibility of the channel')

    class Config:
        orm_mode = True


class PaginatedResponse(GenericModel, Generic[T]):
    pagination: Pagination = Field(None, title="Pagination object")
    result: List[T] = Field([], title="Result objects")


class PostMember(BaseModel):
    username: str
    role: str = Role


class UserRole(BaseModel):
    role: str = Role


class CPRole(BaseModel):
    channel: str
    package: Optional[str]
    role: str = Role


class BaseApiKey(BaseModel):
    description: str
    time_created: Optional[date]
    expire_at: Optional[date]
    roles: Optional[List[CPRole]]


class ApiKey(BaseApiKey):
    key: str


class PackageVersion(BaseModel):
    id: uuid.UUID
    channel_name: str
    package_name: str
    platform: str
    version: str
    build_string: str
    build_number: int

    filename: str
    info: dict
    uploader: BaseProfile
    time_created: datetime
    download_count: int

    class Config:
        orm_mode = True

    @validator("uploader", pre=True)
    def convert_uploader(cls, v):
        if hasattr(v, "profile"):
            return v.profile
        else:
            return v

    @validator("info", pre=True)
    def load_json(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        else:
            return v


class ChannelAction(BaseModel):
    action: ChannelActionEnum
    start_at: Optional[datetime]
    repeat_every_seconds: Optional[int]
