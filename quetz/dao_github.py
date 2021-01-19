# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import rest_models
from .authorization import OWNER
from .config import Config
from .dao import Dao
from .db_models import Channel, Identity, User
from .errors import ValidationError


def create_user_with_github_identity(
    dao: Dao, github_profile: dict, default_role: str, create_default_channel: bool
) -> User:

    username = github_profile["login"]
    user = dao.create_user_with_profile(
        username=username,
        provider=github_profile['provider'],
        identity_id=github_profile["id"],
        name=github_profile["name"],
        avatar_url=github_profile["avatar_url"],
        role=default_role,
        exist_ok=False,
    )

    if create_default_channel:

        channel_name = username

        i = 0

        while dao.db.query(Channel).filter(Channel.name == channel_name).one_or_none():

            channel_name = f"{username}-{i}"

            i += 1

        channel_meta = rest_models.Channel(
            name=channel_name,
            description=f"{username}'s default channel",
            private=True,
        )

        dao.create_channel(channel_meta, user.id, OWNER)

    return user


def user_github_profile_changed(user, identity, profile):
    if (
        identity.username != profile['login']
        or user.profile.name != profile['name']
        or user.profile.avatar_url != profile['avatar_url']
    ):
        return True

    return False


def update_user_from_github_profile(db: Session, user, identity, profile) -> User:

    identity.username = profile['login']
    user.profile.name = profile['name']
    user.profile.avatar_url = profile['avatar_url']

    db.commit()
    db.refresh(user)
    return user


def get_user_by_github_identity(dao: Dao, profile: dict, config: Config) -> User:

    db = dao.db
    provider = profile.get("provider", "github")

    try:
        user, identity = db.query(User, Identity).join(Identity).filter(
            Identity.provider == provider
        ).filter(Identity.identity_id == str(profile['id']),).one_or_none() or (
            None,
            None,
        )
    except KeyError:
        print(f"unexpected response format: {profile}")

    if config.configured_section("users"):
        default_role = config.users_default_role
        create_default_channel = config.users_create_default_channel
    else:
        default_role = None
        create_default_channel = False

    if user:
        if user_github_profile_changed(user, identity, profile):
            return update_user_from_github_profile(db, user, identity, profile)
        return user

    try:
        user = create_user_with_github_identity(
            dao, profile, default_role, create_default_channel
        )
    except IntegrityError:
        raise ValidationError(f"user name '{profile['login']}' already exists")

    return user
