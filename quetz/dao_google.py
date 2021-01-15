# Copyright 2020 QuantStack, Codethink Ltd
# Distributed under the terms of the Modified BSD License.

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import rest_models
from .authorization import OWNER
from .config import Config
from .dao import Dao
from .db_models import Channel, Identity, User
from .errors import ValidationError


def create_user_with_google_identity(
    dao: Dao, google_profile: dict, default_role: str, create_default_channel: bool
) -> User:

    username = google_profile['email']
    user = dao.create_user_with_profile(
        username=username,
        provider="google",
        identity_id=google_profile["sub"],
        name=google_profile["name"],
        avatar_url=google_profile['picture'],
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


def user_google_profile_changed(user, identity, profile):
    if (
        identity.username != profile['email']
        or user.profile.name != profile['name']
        or user.profile.avatar_url != profile['picture']
    ):
        return True

    return False


def update_user_from_google_profile(db: Session, user, identity, profile) -> User:
    identity.username = profile['email']
    user.profile.name = profile['name']
    user.profile.avatar_url = profile['picture']

    db.commit()
    db.refresh(user)
    return user


def get_user_by_google_identity(dao: Dao, profile: dict, config: Config) -> User:

    db = dao.db

    try:
        user, identity = db.query(User, Identity).join(Identity).filter(
            Identity.provider == 'google'
        ).filter(Identity.identity_id == str(profile['sub'])).one_or_none() or (
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
        if user_google_profile_changed(user, identity, profile):
            return update_user_from_google_profile(db, user, identity, profile)
        return user

    try:
        user = create_user_with_google_identity(
            dao, profile, default_role, create_default_channel
        )
    except IntegrityError:
        raise ValidationError(f"user name {profile['email']} already exists")

    return user
