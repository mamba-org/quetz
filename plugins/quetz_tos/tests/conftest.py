import uuid

from pytest import fixture
from quetz_tos import db_models

from quetz.db_models import Profile, User

pytest_plugins = "quetz.testing.fixtures"


@fixture
def owner_user(db):
    user = User(id=uuid.uuid4().bytes, username="madhurt", role="owner")
    db.add(user)
    db.commit()

    yield user

    db.delete(user)
    db.commit()


@fixture
def member_user(db):
    user = User(id=uuid.uuid4().bytes, username="alice", role="member")
    db.add(user)
    db.commit()

    yield user

    db.delete(user)
    db.commit()


@fixture
def tos(db, owner_user):
    tos = db_models.TermsOfService(
        uploader_id=owner_user.id,
        filename="tos.txt",
    )

    db.add(tos)
    db.commit()

    yield tos

    db.delete(tos)
    db.commit()


@fixture
def tos_file(config):
    pkgstore = config.get_package_store()
    pkgstore.add_file(b"demo tos", "root", "tos.txt")


@fixture
def tos_sign(db, tos, member_user):
    tos_sign = db_models.TermsOfServiceSignatures(
        tos_id=tos.id,
        user_id=member_user.id,
    )

    db.add(tos_sign)
    db.commit()

    yield tos_sign

    db.delete(tos_sign)
    db.commit()
