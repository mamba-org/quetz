from pathlib import Path

import pytest

from quetz.config import Config
from quetz.dao import Dao
from quetz.jobs.models import Job, JobStatus, Task
from quetz.jobs.runner import run_jobs, run_tasks
from quetz.rest_models import Channel, Package
from quetz.tasks.workers import SubprocessWorker

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def package_name():
    return "my-package"


@pytest.fixture
def channel_name():
    return "my-channel"


@pytest.fixture
def private_channel(dao, other_user):

    channel_name = "private-channel"

    channel_data = Channel(name=channel_name, private=True)
    channel = dao.create_channel(channel_data, other_user.id, "owner")

    return channel


@pytest.fixture
def private_package(dao, other_user, private_channel):

    package_name = "private-package"
    package_data = Package(name=package_name)
    package = dao.create_package(
        private_channel.name, package_data, other_user.id, "owner"
    )

    return package


@pytest.fixture
def private_package_version(dao, private_channel, private_package, other_user, config):
    package_format = "tarbz2"
    package_info = "{}"
    channel_name = private_channel.name
    filename = Path("test-package-0.1-0.tar.bz2")

    pkgstore = config.get_package_store()
    with open(filename, "rb") as fid:
        pkgstore.add_file(fid.read(), channel_name, "linux-64" / filename)

    version = dao.create_version(
        private_channel.name,
        private_package.name,
        package_format,
        "linux-64",
        "0.1",
        "0",
        "",
        str(filename),
        package_info,
        other_user.id,
        size=0,
    )

    return version


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
    filename = Path("test-package-0.1-0.tar.bz2")
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

    db.delete(version)
    db.commit()


@pytest.fixture
def channel_role():
    return "owner"


@pytest.fixture
def package_role():
    return "owner"


@pytest.fixture
def public_channel(dao: Dao, user, channel_role, channel_name):

    channel_data = Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, channel_role)

    return channel


@pytest.fixture
def public_package(db, user, public_channel, dao, package_role, package_name):

    package_data = Package(name=package_name)

    package = dao.create_package(
        public_channel.name, package_data, user.id, package_role
    )

    return package


def test_create_task(config, db, user, package_version):
    job = Job(owner_id=user.id, manifest="")
    task = Task(job=job)
    db.add(job)
    db.add(task)
    db.commit()


def func(package_version: dict):
    pass


@pytest.mark.asyncio
async def test_create_job(config, db, user, package_version):
    import pickle

    func_serialized = pickle.dumps(func)
    job = Job(owner_id=user.id, manifest=func_serialized)
    manager = SubprocessWorker("", {}, config)
    db.add(job)
    db.commit()
    run_jobs(db)
    await run_tasks(db, manager)
    jobs = db.query(Job).all()
    tasks = db.query(Task).all()

    assert len(jobs) == 1
    assert jobs[0].status == JobStatus.running

    assert len(tasks) == 1
