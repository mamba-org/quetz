import pytest
from sqlalchemy.exc import IntegrityError

from quetz.dao import Dao
from quetz.db_models import PackageVersion
from quetz.rest_models import Channel, Package


@pytest.fixture
def dao(db) -> Dao:
    return Dao(db)


@pytest.fixture
def package_name():
    return "my-package"


@pytest.fixture
def channel_name():
    return "my-channel"


@pytest.fixture
def package(dao, channel_name, package_name, user, db):
    channel_data = Channel(name=channel_name, private=False)
    package_data = Package(name=package_name)

    channel, channel_member = dao.create_channel(channel_data, user.id, "owner")
    package, package_member = dao.create_package(
        channel_name, package_data, user.id, "owner"
    )

    yield package

    db.delete(channel_member)
    db.delete(package)
    db.delete(package_member)
    db.delete(channel)
    db.commit()


def test_create_version(dao, package, channel_name, package_name, db, user):

    assert (
        not db.query(PackageVersion)
        .filter(PackageVersion.package_name == package_name)
        .first()
    )
    assert dao.db == db
    dao.create_version(
        channel_name=channel_name,
        package_name=package_name,
        package_format="tarbz2",
        platform="noarch",
        version="0.0.1",
        build_number="0",
        build_string="",
        filename="filename.tar.bz2",
        info="{}",
        uploader_id=user.id,
        upsert=False,
    )

    created_version = (
        db.query(PackageVersion)
        .filter(PackageVersion.package_name == package_name)
        .first()
    )

    assert created_version
    assert created_version.version == "0.0.1"
    assert created_version.build_number == 0
    assert created_version.filename == "filename.tar.bz2"
    assert created_version.info == "{}"

    # error for insert-only with existing row
    with pytest.raises(IntegrityError):
        dao.create_version(
            channel_name=channel_name,
            package_name=package_name,
            package_format="tarbz2",
            platform="noarch",
            version="0.0.1",
            build_number="0",
            build_string="",
            filename="filename-2.tar.bz2",
            info="{}",
            uploader_id=user.id,
            upsert=False,
        )

    # update with upsert
    dao.create_version(
        channel_name=channel_name,
        package_name=package_name,
        package_format="tarbz2",
        platform="noarch",
        version="0.0.1",
        build_number="0",
        build_string="",
        filename="filename-2.tar.bz2",
        info='{"version": "x.y.z"}',
        uploader_id=user.id,
        upsert=True,
    )

    created_version = (
        db.query(PackageVersion)
        .filter(PackageVersion.package_name == package_name)
        .first()
    )

    assert created_version
    assert created_version.version == "0.0.1"
    assert created_version.build_number == 0
    assert created_version.filename == "filename-2.tar.bz2"
    assert created_version.info == '{"version": "x.y.z"}'
