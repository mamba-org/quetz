# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from quetz import rest_models
from quetz.authorization import OWNER
from quetz.config import Config
from quetz.dao import Dao
from quetz.db_models import Channel, Email, Identity, User
from quetz.errors import ValidationError

from . import base


def create_user_with_identity(
    dao: Dao,
    provider: str,
    profile: 'base.UserProfile',
    default_role: Optional[str],
    default_channels: Optional[List[str]],
) -> User:

    username = profile["login"]
    user = dao.create_user_with_profile(
        username=username,
        provider=provider,
        emails=profile.get("emails", []),
        identity_id=profile["id"],
        name=profile["name"],
        avatar_url=profile["avatar_url"],
        role=default_role,
        exist_ok=False,
    )

    if default_channels is not None:

        for channel_name in default_channels:

            i = 0

            while (
                dao.db.query(Channel).filter(Channel.name == channel_name).one_or_none()
            ):

                channel_name = f"{username}-{i}"

                i += 1

            channel_meta = rest_models.Channel(
                name=channel_name,
                description=f"{username}'s default channel",
                private=True,
            )

            dao.create_channel(channel_meta, user.id, OWNER)

    return user


def user_profile_changed(user, identity, profile: 'base.UserProfile'):
    if (
        identity.username != profile['login']
        or user.profile.name != profile['name']
        or user.profile.avatar_url != profile['avatar_url']
        or set((e.verified, e.primary, e.email) for e in user.emails)
        != set(
            (e['verified'], e['primary'], e['email']) for e in profile.get('emails', [])
        )
    ):
        return True

    return False


def update_user_from_profile(
    db: Session, user, identity, profile: 'base.UserProfile'
) -> User:

    identity.username = profile['login']
    user.profile.name = profile['name']
    user.profile.avatar_url = profile['avatar_url']

    # check if any email already registered
    emails = []
    for e in profile.get('emails', []):
        if not e["verified"]:
            continue

        user_email = db.query(Email).filter(Email.email == e["email"]).one_or_none()
        if user_email and user_email.user_id != user.id:
            raise IntegrityError(
                f"User {user.profile.name} already registered"
                " with email {user_email.email}",
                "",
                "",
            )

        if user_email and e["verified"]:
            emails.append(user_email)
            user_email.primary = True if e["primary"] else False
        else:
            emails.append(
                Email(
                    email=e["email"],
                    verified=e["verified"],
                    primary=e["primary"],
                    provider=identity.provider,
                    identity_id=identity.identity_id,
                )
            )

    user.emails = emails

    db.commit()
    db.refresh(user)
    return user


def get_user_by_identity(
    dao: Dao,
    provider: str,
    profile: 'base.UserProfile',
    config: Config,
    default_role: Optional[str] = None,
    default_channels: Optional[List[str]] = None,
) -> User:

    db = dao.db

    try:
        user, identity = db.query(User, Identity).join(Identity).filter(
            Identity.provider == provider
        ).filter(Identity.identity_id == str(profile['id']),).one_or_none() or (
            None,
            None,
        )
    except KeyError:
        print(f"unexpected response format: {profile}")

    if user:
        if user_profile_changed(user, identity, profile):
            return update_user_from_profile(db, user, identity, profile)
        return user

    try:
        user = create_user_with_identity(
            dao, provider, profile, default_role, default_channels
        )
    except IntegrityError:
        raise ValidationError(f"user name '{profile['login']}' already exists")

    return user
