# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from sqlalchemy.orm import Session
import uuid

from .db_models import Identity, Profile, User


def create_user_with_github_identity(db: Session, github_profile) -> User:
    user = User(id=uuid.uuid4().bytes, username=github_profile['login'])

    identity = Identity(
        provider='github',
        identity_id=github_profile['id'],
        username=github_profile['login'],
    )

    profile = Profile(
        name=github_profile['name'],
        avatar_url=github_profile['avatar_url'])

    user.identities.append(identity)
    user.profile = profile
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_github_identity(db: Session, profile) -> User:
    user = db.query(User).join(Identity) \
        .filter(Identity.provider == 'github') \
        .filter(Identity.identity_id == profile['id']) \
        .one_or_none()

    if user:
        return user

    return create_user_with_github_identity(db, profile)
