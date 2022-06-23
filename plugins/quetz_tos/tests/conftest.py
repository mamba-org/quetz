import uuid

from pytest import fixture
from quetz_tos import db_models

from quetz.db_models import User

pytest_plugins = "quetz.testing.fixtures"


@fixture
def owner_user(db):
    user = User(id=uuid.uuid4().bytes, username="madhurt", role="owner")
    db.add(user)
    db.commit()

    yield user


@fixture
def member_user(db):
    user = User(id=uuid.uuid4().bytes, username="alice", role="member")
    db.add(user)
    db.commit()

    yield user


@fixture
def tos(db, owner_user):
    tos = db_models.TermsOfService(
        uploader_id=owner_user.id, filename="tos_en.txt", language="EN"
    )

    tos2 = db_models.TermsOfService(
        uploader_id=owner_user.id, filename="tos_fr.txt", language="FR"
    )

    db.add(tos)
    db.add(tos2)
    db.commit()

    yield [tos, tos2]


@fixture
def tos_file(config):
    pkgstore = config.get_package_store()
    pkgstore.add_file(b"demo tos", "root", "tos_en.txt")
    pkgstore.add_file(b"demo tos", "root", "tos_fr.txt")


@fixture
def tos_sign(db, tos, member_user):
    all_signed_tos = []
    for a_tos in tos:
        tos_sign = db_models.TermsOfServiceSignatures(
            tos_id=a_tos.id,
            user_id=member_user.id,
        )

        db.add(tos_sign)
        all_signed_tos.append(tos_sign)
    db.commit()
    yield all_signed_tos
