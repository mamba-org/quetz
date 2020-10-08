# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import uuid

from sqlalchemy.orm import Session

from .db_models import Identity, Profile, User


def create_user_with_github_identity(db: Session, github_profile) -> User:

    # retrieve user if already exists
    user = db.query(User).filter_by(username=github_profile['login']).first()

    if not user:
        user = User(id=uuid.uuid4().bytes, username=github_profile['login'])

    identity = Identity(
        provider='github',
        identity_id=github_profile['id'],
        username=github_profile['login'],
    )

    profile = Profile(
        name=github_profile['name'], avatar_url=github_profile['avatar_url']
    )

    user.identities.append(identity)
    user.profile = profile
    db.add(user)
    db.commit()
    db.refresh(user)
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


def get_user_by_github_identity(db: Session, profile) -> User:
    user, identity = db.query(User, Identity).join(Identity).filter(
        Identity.provider == 'github'
    ).filter(Identity.identity_id == str(profile['id'])).one_or_none() or (None, None)

    if user:
        if user_github_profile_changed(user, identity, profile):
            return update_user_from_github_profile(db, user, identity, profile)
        return user

    return create_user_with_github_identity(db, profile)
