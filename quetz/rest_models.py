# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field
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
    id: str
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


class Channel(BaseModel):
    name: str = Field(None, title='The name of the channel', max_length=50)
    description: str = Field(
        None, title='The description of the channel', max_length=300
    )
    private: bool
    mirror: bool = False

    class Config:
        orm_mode = True


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
