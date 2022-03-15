import uuid
from datetime import date
from pathlib import Path

import pytest

from quetz.authorization import SERVER_OWNER
from quetz.config import Config
from quetz.dao import Dao
from quetz.db_models import ApiKey, Profile, User
from quetz.jobs.runner import Supervisor
from quetz.rest_models import Channel, Package
from quetz.testing.mockups import MockWorker

pytest_plugins = "quetz.testing.fixtures"


@pytest.fixture
def plugins():
    # defines plugins to enable for testing
    return ['quetz-harvester']


@pytest.fixture
def user_role():
    return SERVER_OWNER


@pytest.fixture
def user(db, user_role):

    new_user = User(id=uuid.uuid4().bytes, username="bartosz", role=user_role)
    profile = Profile(name="Bartosz", avatar_url="http:///avatar", user=new_user)
    db.add(profile)
    db.add(new_user)
    db.commit()

    yield new_user

    db.delete(new_user)
    db.commit()


@pytest.fixture
def supervisor(config, db, dao):
    manager = MockWorker(config, db, dao)
    supervisor = Supervisor(db, manager)
    return supervisor


@pytest.fixture
def package_name():
    return "xtensor-io"


@pytest.fixture
def channel_name():
    return "my-channel"


@pytest.fixture
def package_version(
    db,
    user,
    public_channel,
    channel_name,
    package_name,
    public_package,
    dao: Dao,
    config: Config,
):

    pkgstore = config.get_package_store()
    filename = Path(__file__).parent / "data" / "xtensor-io-0.10.3-hb585cf6_0.tar.bz2"
    with open(filename, "rb") as fid:
        pkgstore.add_file(fid.read(), channel_name, "linux-64" / filename)
    package_format = "tarbz2"
    package_info = "{}"
    version = dao.create_version(
        channel_name,
        package_name,
        package_format,
        "linux-64",
        "0.1",
        0,
        "",
        str(filename),
        package_info,
        user.id,
        size=11,
    )

    dao.update_channel_size(channel_name)
    db.refresh(public_channel)

    yield version

    try:
        db.delete(version)
        db.commit()
    except Exception:
        pass


@pytest.fixture
def channel_role():
    return "owner"


@pytest.fixture
def package_role():
    return "owner"


@pytest.fixture
def public_channel(dao: Dao, user, channel_role, channel_name, db):

    channel_data = Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, channel_role)

    yield channel
    db.delete(channel)
    db.commit()


@pytest.fixture
def public_package(db, user, public_channel, dao, package_role, package_name):

    package_data = Package(name=package_name)

    package = dao.create_package(
        public_channel.name, package_data, user.id, package_role
    )

    yield package

    db.delete(package)
    db.commit()


@pytest.fixture
def auto_rollback():
    # we are comparing database content across processes, so need to
    # disable the rollback mechanism
    return False


@pytest.fixture
def sqlite_in_memory():
    # use sqlite on disk so that we can modify it in a different process
    return False


@pytest.fixture
def api_key(db, user):

    key = ApiKey(
        key="apikey",
        time_created=date.today(),
        expire_at=date(2030, 1, 1),
        user_id=user.id,
        owner_id=user.id,
    )
    db.add(key)
    db.commit()
    return key
