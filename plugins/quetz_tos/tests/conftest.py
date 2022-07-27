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
    tos_en = db_models.TermsOfServiceFile(filename="tos_en.txt", language="EN")
    tos_fr = db_models.TermsOfServiceFile(filename="tos_fr.txt", language="FR")

    tos = db_models.TermsOfService(uploader_id=owner_user.id, files=[tos_en, tos_fr])

    db.add(tos)
    db.commit()

    yield tos


@fixture
def tos_file(config):
    pkgstore = config.get_package_store()
    pkgstore.add_file(b"demo tos en", "root", "tos_en.txt")
    pkgstore.add_file(b"demo tos fr", "root", "tos_fr.txt")


@fixture
def tos_sign(db, tos, member_user):
    tos_sign = db_models.TermsOfServiceSignatures(
        tos_id=tos.id,
        user_id=member_user.id,
    )

    db.add(tos_sign)
    db.commit()

    yield tos_sign
