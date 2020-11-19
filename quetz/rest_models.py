# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field, root_validator
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


class Member(BaseModel):
    role: str
    user: User

    class Config:
        orm_mode = True


Role = Field(None, regex='owner|maintainer|member')


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
    private: bool
    mirror_channel_url: Optional[str] = Field(None, regex="^(http|https)://.+")
    mirror_mode: Optional[MirrorMode] = None

    class Config:
        orm_mode = True


class ChannelActionEnum(str, Enum):
    synchronize = 'synchronize'
    reindex = "reindex"


class ChannelMetadata(BaseModel):

    actions: Optional[List[ChannelActionEnum]] = Field(
        None, title="list of actions to run after channel creation"
    )


class Channel(ChannelBase):

    metadata: ChannelMetadata = Field(
        default_factory=ChannelMetadata, title="channel metadata"
    )

    @root_validator
    def check_passwords_match(cls, values):
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


class Package(BaseModel):
    name: str = Field(None, title='The name of package', max_length=50)
    summary: str = Field(None, title='The summary of the package')
    description: str = Field(None, title='The description of the package')

    class Config:
        orm_mode = True


class PackageSearch(BaseModel):
    name: str = Field(None, title='The name of package', max_length=50)
    summary: str = Field(None, title='The summary of the package')
    description: str = Field(None, title='The description of the package')
    channel_name: str = Field(None, title='The channel this package belongs to')

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
    roles: List[CPRole]


class ApiKey(BaseApiKey):
    key: str


class PackageVersion(BaseModel):
    id: str
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

    class Config:
        orm_mode = True


class ChannelAction(BaseModel):
    action: ChannelActionEnum
