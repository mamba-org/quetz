# Copyright 2020 QuantStack, Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import uuid

from sqlalchemy.orm import Session

from .db_models import Identity, Profile, User


def create_user_with_google_identity(db: Session, google_profile) -> User:
    user = User(id=uuid.uuid4().bytes, username=google_profile['email'])

    identity = Identity(
        provider='google',
        identity_id=google_profile['sub'],
        username=google_profile['email'],
    )

    profile = Profile(name=google_profile['name'], avatar_url=google_profile['picture'])

    user.identities.append(identity)  # type: ignore
    user.profile = profile
    db.add(user)
    db.commit()
    db.refresh(user)
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


def get_user_by_google_identity(db: Session, profile) -> User:
    user, identity = db.query(User, Identity).join(Identity).filter(
        Identity.provider == 'google'
    ).filter(Identity.identity_id == profile['sub']).one_or_none() or (None, None)

    if user:
        if user_google_profile_changed(user, identity, profile):
            return update_user_from_google_profile(db, user, identity, profile)
        return user

    return create_user_with_google_identity(db, profile)
