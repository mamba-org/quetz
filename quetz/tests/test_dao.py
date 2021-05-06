import datetime
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import ObjectDeletedError

from quetz import errors, rest_models
from quetz.dao import Dao
from quetz.database import get_session
from quetz.db_models import Channel, Package, PackageVersion
from quetz.metrics.db_models import IntervalType, PackageVersionMetric, round_timestamp


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

    try:
        db.delete(channel)
        db.commit()
    except ObjectDeletedError:
        pass


@pytest.fixture
def package(dao, channel, package_name, user, db):
    package_data = rest_models.Package(name=package_name)

    package = dao.create_package(channel.name, package_data, user.id, "owner")

    yield package

    db.delete(package)
    db.commit()


@pytest.fixture
def package_version(dao, package, user):
    return dao.create_version(
        channel_name=package.channel_name,
        package_name=package.name,
        package_format="tarbz2",
        platform="noarch",
        version="0.0.1",
        build_number="0",
        build_string="",
        filename="filename.tar.bz2",
        info="{}",
        uploader_id=user.id,
        size=101,
        upsert=False,
    )


def test_channel_with_huge_size_limit(dao, user, db):
    channel_data = rest_models.Channel(
        name="my-channel", private=False, size_limit=1000000000000000000
    )
    channel = dao.create_channel(channel_data, user.id, "owner", 1000000000000000000)
    del channel


def test_create_channel_with_invalid_name(dao, user, db):
    with pytest.raises(errors.ValidationError):
        channel_data = rest_models.Channel(name="my_channel", private=False)
        channel = dao.create_channel(channel_data, user.id, "owner")
        del channel


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
        size=0,
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
            size=0,
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
        size=0,
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


def test_update_channel_size(dao, channel, db, package_version):

    dao.update_channel_size(channel.name)

    channel = db.query(Channel).filter(Channel.name == channel.name).one()

    assert channel.size == package_version.size


def test_increment_download_count(
    dao: Dao, channel, db, package_version, session_maker
):

    assert package_version.download_count == 0
    now = datetime.datetime(2020, 10, 1, 10, 1, 10)
    dao.incr_download_count(
        channel.name, package_version.filename, package_version.platform, timestamp=now
    )

    download_counts = db.query(PackageVersionMetric).all()
    for m in download_counts:
        assert m.count == 1

    assert len(download_counts) == len(IntervalType)

    db.refresh(package_version)
    assert package_version.download_count == 1

    dao.incr_download_count(
        channel.name, package_version.filename, package_version.platform, timestamp=now
    )
    download_counts = db.query(PackageVersionMetric).all()
    for m in download_counts:
        assert m.count == 2

    assert len(download_counts) == len(IntervalType)

    db.refresh(package_version)
    assert package_version.download_count == 2

    dao.incr_download_count(
        channel.name,
        package_version.filename,
        package_version.platform,
        timestamp=now + datetime.timedelta(days=1),
    )

    download_counts = db.query(PackageVersionMetric).all()
    assert len(download_counts) == len(IntervalType) + 2

    db.refresh(package_version)
    assert package_version.download_count == 3


def test_get_package_version_metrics(dao: Dao, channel, db, package_version):

    now = datetime.datetime(2020, 10, 1, 10, 1, 10)
    dao.incr_download_count(
        channel.name, package_version.filename, package_version.platform, timestamp=now
    )

    metrics = dao.get_package_version_metrics(
        package_version.id, IntervalType.hour, "download"
    )

    metrics_dict = [(m.timestamp, m.count) for m in metrics]
    timestamp = now.replace(minute=0, second=0)

    assert metrics_dict == [(timestamp, 1)]

    hour = datetime.timedelta(hours=1)
    day = datetime.timedelta(days=1)

    metrics = dao.get_package_version_metrics(
        package_version.id,
        IntervalType.hour,
        "download",
        start=now - hour,
        end=now + hour,
    )

    metrics_dict = [(m.timestamp, m.count) for m in metrics]
    assert metrics_dict == [(timestamp, 1)]

    metrics = dao.get_package_version_metrics(
        package_version.id,
        IntervalType.hour,
        "download",
        start=now - hour,
        end=now + hour,
        fill_zeros=True,
    )

    metrics_dict = [(m.timestamp, m.count) for m in metrics]
    assert metrics_dict == [
        (timestamp - hour, 0),
        (timestamp, 1),
        (timestamp + hour, 0),
    ]

    # no start/end

    metrics = dao.get_package_version_metrics(
        package_version.id,
        IntervalType.hour,
        "download",
        start=now - hour,
        fill_zeros=True,
    )
    metrics_dict = [(m.timestamp, m.count) for m in metrics]
    assert metrics_dict == [
        (timestamp - hour, 0),
        (timestamp, 1),
    ]

    metrics = dao.get_package_version_metrics(
        package_version.id,
        IntervalType.hour,
        "download",
        end=now + hour,
        fill_zeros=True,
    )
    metrics_dict = [(m.timestamp, m.count) for m in metrics]
    assert metrics_dict == [
        (timestamp, 1),
        (timestamp + hour, 0),
    ]

    metrics = dao.get_package_version_metrics(
        package_version.id,
        IntervalType.hour,
        "download",
        fill_zeros=True,
    )
    metrics_dict = [(m.timestamp, m.count) for m in metrics]
    assert metrics_dict == [
        (timestamp, 1),
    ]

    # day interval
    timestamp_day = timestamp.replace(hour=0)
    metrics = dao.get_package_version_metrics(
        package_version.id, IntervalType.day, "download"
    )
    metrics_dict = [(m.timestamp, m.count) for m in metrics]
    assert metrics_dict == [(timestamp_day, 1)]

    metrics = dao.get_package_version_metrics(
        package_version.id,
        IntervalType.day,
        "download",
        start=now - day,
        end=now + day,
        fill_zeros=True,
    )

    metrics_dict = [(m.timestamp, m.count) for m in metrics]
    assert metrics_dict == [
        (timestamp_day - day, 0),
        (timestamp_day, 1),
        (timestamp_day + day, 0),
    ]

    # two items
    dao.incr_download_count(
        channel.name,
        package_version.filename,
        package_version.platform,
        timestamp=now + datetime.timedelta(hours=2),
    )

    metrics = dao.get_package_version_metrics(
        package_version.id,
        IntervalType.hour,
        "download",
        fill_zeros=True,
    )
    metrics_dict = [(m.timestamp, m.count) for m in metrics]
    assert metrics_dict == [
        (timestamp, 1),
        (timestamp + hour, 0),
        (timestamp + 2 * hour, 1),
    ]


@pytest.mark.parametrize("interval", list(IntervalType))
def test_get_package_version_metrics_intervals(
    dao: Dao, channel, db, package_version, interval
):

    now = datetime.datetime(2020, 10, 1, 10, 1, 10)
    dao.incr_download_count(
        channel.name, package_version.filename, package_version.platform, timestamp=now
    )

    metrics = dao.get_package_version_metrics(package_version.id, interval, "download")
    timestamp_interval = round_timestamp(now, interval)
    metrics_dict = [(m.timestamp, m.count) for m in metrics]
    assert metrics_dict == [(timestamp_interval, 1)]

    end = timestamp_interval.replace(year=2021)
    metrics = dao.get_package_version_metrics(
        package_version.id,
        interval,
        "download",
        start=timestamp_interval,
        end=end,
        fill_zeros=True,
    )

    metrics_dict = [(m.timestamp, m.count) for m in metrics]

    assert metrics_dict[0] == (timestamp_interval, 1)
    assert metrics_dict[-1] == (end, 0)


def test_create_user_with_profile(dao: Dao, user_without_profile):

    user = dao.create_user_with_profile(
        user_without_profile.username,
        provider="github",
        identity_id="1",
        name="new user",
        avatar_url="http://avatar",
        emails=None,
        role=None,
        exist_ok=True,
    )

    assert user.profile

    with pytest.raises(IntegrityError):
        dao.create_user_with_profile(
            user_without_profile.username,
            provider="github",
            identity_id="1",
            name="new user",
            avatar_url="http://avatar",
            role=None,
            exist_ok=False,
        )


@pytest.fixture
def db_extra(database_url):
    """a separate session for db connection

    Use only for tests that require two sessions concurrently.
    For most cases you will want to use the db fixture (from quetz.testing.fixtures)"""

    session = get_session(database_url)

    yield session

    session.close()


@pytest.fixture
def dao_extra(db_extra):

    return Dao(db_extra)


@pytest.fixture
def user_with_channel(dao, db, use_migrations, sqlite_in_memory):
    channel_data = rest_models.Channel(name="new-test-channel", private=False)

    user = dao.create_user_with_role("new-user")
    user_id = user.id
    channel = dao.create_channel(channel_data, user_id, "owner")
    db.commit()

    yield user_id
    db.delete(channel)
    db.delete(user)
    db.commit()


# disable running tests in transaction and use on disk database
# because we want to connect to the db with two different
# client concurrently
@pytest.mark.parametrize("sqlite_in_memory", [False])
@pytest.mark.parametrize("auto_rollback", [False])
def test_rollback_on_collision(
    dao: Dao, db, dao_extra, user_with_channel, use_migrations
):
    """testing rollback on concurrent writes."""

    new_package = rest_models.Package(name=f"new-package-{uuid.uuid4()}")

    user_id = user_with_channel
    channel_name = "new-test-channel"

    dao.create_package(channel_name, new_package, user_id, "owner")
    with pytest.raises(errors.DBError, match="(IntegrityError)|(UniqueViolation)"):
        dao_extra.create_package(channel_name, new_package, user_id, "owner")

    requested = db.query(Package).filter(Package.name == new_package.name).one_or_none()

    assert requested

    # need to clean up because we didn't run the test in a transaction

    db.delete(requested)
    db.commit()
