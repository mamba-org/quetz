# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from pydantic import BaseModel, Field
from typing import List
from datetime import datetime


class Profile(BaseModel):
    name: str
    avatar_url: str

    class Config:
        orm_mode = True


class User(BaseModel):
    id: str
    username: str
    profile: Profile

    class Config:
        orm_mode = True


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
    package: str
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
