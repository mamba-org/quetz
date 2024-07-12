import json
import uuid

from pytest import fixture
from sqlalchemy.orm import Session

from plugins.quetz_runexports.quetz_runexports.db_models import PackageVersionMetadata
from quetz import rest_models
from quetz.dao import Dao
from quetz.db_models import User, PackageVersion, Package, Channel

pytest_plugins = "quetz.testing.fixtures"


@fixture
def dao(db) -> Dao:
    return Dao(db)


@fixture
def user(db: Session) -> User:
    user = User(id=uuid.uuid4().bytes, username="bartosz")
    db.add(user)
    db.commit()
    yield user


@fixture
def channel(dao: Dao, user: User, db: Session):
    channel_data = rest_models.Channel(
        name="test-mirror-channel",
        private=False,
        mirror_channel_url="http://host",
        mirror_mode="mirror",
    )

    channel = dao.create_channel(channel_data, user.id, "owner")

    yield channel

    db.delete(channel)
    db.commit()


@fixture
def package(dao: Dao, user: User, channel: Channel, db: Session) -> Package:
    new_package_data = rest_models.Package(name="test-package")

    package = dao.create_package(
        channel.name,
        new_package_data,
        user_id=user.id,
        role="owner",
    )

    yield package

    db.delete(package)
    db.commit()


@fixture
def package_version(
    dao: Dao, user: User, channel: Channel, db: Session, package: Package
) -> PackageVersion:
    # create package version that will added to local repodata
    package_format = "tarbz2"
    package_info = '{"size": 5000, "subdirs":["noarch"]}'

    version = dao.create_version(
        channel.name,
        package.name,
        package_format,
        "noarch",
        "0.1",
        "0",
        "0",
        "test-package-0.1-0.tar.bz2",
        package_info,
        user.id,
        size=5000,
    )

    yield version

    db.delete(version)
    db.commit()


@fixture
def package_runexports(
    db: Session, package_version: PackageVersion
) -> PackageVersionMetadata:
    meta = PackageVersionMetadata(
        version_id=package_version.id,
        data=json.dumps({"weak": ["somepackage > 3.0"]}),
    )

    db.add(meta)
    db.commit()

    yield meta

    db.delete(meta)
    db.commit()
