import pytest
from sqlalchemy.exc import IntegrityError

from quetz import rest_models
from quetz.db_models import Channel, PackageVersion


@pytest.fixture
def package_name():
    return "my-package"


@pytest.fixture
def channel_name():
    return "my-channel"


@pytest.fixture
def channel(dao, db, user, channel_name):

    channel_data = rest_models.Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, "owner")
    yield channel

    db.delete(channel)
    db.commit()


@pytest.fixture
def package(dao, channel, package_name, user, db):
    package_data = rest_models.Package(name=package_name)

    package = dao.create_package(channel.name, package_data, user.id, "owner")

    yield package

    db.delete(package)
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
    assert created_version.time_created == created_version.time_modified

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
    assert created_version.time_created != created_version.time_modified


def test_update_channel(dao, channel, db):

    assert not channel.private
    dao.update_channel(channel.name, {"private": True})

    channel = db.query(Channel).filter(Channel.name == channel.name).one()

    assert channel.private
