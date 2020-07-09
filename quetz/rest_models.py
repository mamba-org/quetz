# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


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


class Channel(BaseModel):
    name: str = Field(None, title='The name of the channel', max_length=50)
    description: str = Field(None, title='The description of the channel', max_length=300)
    private: bool

    class Config:
        orm_mode = True


class Package(BaseModel):
    name: str = Field(None, title='The name of package', max_length=50)
    description: str = Field(None, title='The description of the package', max_length=300)

    class Config:
        orm_mode = True


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
    uploader: Profile
    time_created: datetime

    class Config:
        orm_mode = True
