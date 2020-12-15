import os
import pickle
from pathlib import Path

import pytest

from quetz.config import Config
from quetz.dao import Dao
from quetz.jobs.models import Job, JobStatus, Task, TaskStatus
from quetz.jobs.runner import (
    check_status,
    mk_sql_expr,
    parse_conda_spec,
    run_jobs,
    run_tasks,
)
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
    job = Job(owner_id=user.id, manifest=b"")
    task = Task(job=job)
    db.add(job)
    db.add(task)
    db.commit()


def func(package_version: dict, config: Config):
    with open("test-output.txt", "w") as fid:
        fid.write("ok")


def failed_func(package_version: dict):
    raise Exception("some exception")


@pytest.mark.asyncio
async def test_create_job(config, db, user, package_version):

    func_serialized = pickle.dumps(func)
    job = Job(owner_id=user.id, manifest=func_serialized)
    manager = SubprocessWorker("", {}, config)
    db.add(job)
    db.commit()
    run_jobs(db)
    new_jobs = run_tasks(db, manager)
    db.refresh(job)
    task = db.query(Task).one()

    assert job.status == JobStatus.running

    assert task.status == TaskStatus.running

    # wait for job to finish
    await new_jobs[0].wait()

    check_status(db)

    db.refresh(task)
    assert task.status == TaskStatus.success
    assert os.path.isfile("test-output.txt")

    db.refresh(job)
    assert job.status == JobStatus.success


@pytest.mark.asyncio
async def test_failed_task(config, db, user, package_version):

    func_serialized = pickle.dumps(failed_func)
    job = Job(owner_id=user.id, manifest=func_serialized)
    manager = SubprocessWorker("", {}, config)
    db.add(job)
    db.commit()
    run_jobs(db)
    new_jobs = run_tasks(db, manager)
    task = db.query(Task).one()
    with pytest.raises(Exception, match="some exception"):
        await new_jobs[0].wait()

    check_status(db)

    db.refresh(task)
    assert task.status == TaskStatus.failed

    db.refresh(job)
    assert job.status == JobStatus.success


def test_mk_query():
    def compile(dict_spec):
        s = mk_sql_expr(dict_spec)
        sql_expr = str(s.compile(compile_kwargs={"literal_binds": True}))
        return sql_expr

    spec = [{"version": ("eq", "0.1"), "package_name": ("in", ["my-package"])}]
    sql_expr = compile(spec)

    assert sql_expr == (
        "package_versions.version = '0.1' "
        "AND package_versions.package_name IN ('my-package')"
    )

    spec = [{"version": ("lt", "0.2")}]
    sql_expr = compile(spec)

    assert sql_expr == "package_versions.version < '0.2'"

    spec = [{"version": ("lte", "0.2")}]
    sql_expr = compile(spec)

    assert sql_expr == "package_versions.version <= '0.2'"

    spec = [{"version": ("gte", "0.3")}]
    sql_expr = compile(spec)

    assert sql_expr == "package_versions.version >= '0.3'"

    spec = [
        {"version": ("lt", "0.2"), "package_name": ("eq", "my-package")},
        {"version": ("gt", "0.3"), "package_name": ("eq", "other-package")},
    ]
    sql_expr = compile(spec)

    assert sql_expr == (
        "package_versions.version < '0.2' "
        "AND package_versions.package_name = 'my-package' "
        "OR package_versions.version > '0.3' "
        "AND package_versions.package_name = 'other-package'"
    )

    spec = [
        {"version": ("and", ("lt", "0.2"), ("gt", "0.1"))},
    ]
    sql_expr = compile(spec)

    assert sql_expr == (
        "package_versions.version < '0.2'" " AND package_versions.version > '0.1'"
    )

    spec = [
        {"version": ("or", ("and", ("lt", "0.2"), ("gt", "0.1")), ("gt", "0.3"))},
    ]
    sql_expr = compile(spec)
    assert sql_expr == (
        "package_versions.version < '0.2'"
        " AND package_versions.version > '0.1'"
        " OR package_versions.version > '0.3'"
    )


def test_parse_conda_spec():

    dict_spec = parse_conda_spec("my-package==0.1.1")
    assert dict_spec == [
        {"version": ("eq", "0.1.1"), "package_name": ("eq", "my-package")}
    ]

    dict_spec = parse_conda_spec("my-package==0.1.2,other-package==0.5.1")
    assert dict_spec == [
        {"version": ("eq", "0.1.2"), "package_name": ("eq", "my-package")},
        {"version": ("eq", "0.5.1"), "package_name": ("eq", "other-package")},
    ]
    dict_spec = parse_conda_spec("my-package>0.1.2")
    assert dict_spec == [
        {"version": ("gt", "0.1.2"), "package_name": ("eq", "my-package")},
    ]

    dict_spec = parse_conda_spec("my-package<0.1.2")
    assert dict_spec == [
        {"version": ("lt", "0.1.2"), "package_name": ("eq", "my-package")},
    ]

    dict_spec = parse_conda_spec("my-package>=0.1.2")
    assert dict_spec == [
        {"version": ("gte", "0.1.2"), "package_name": ("eq", "my-package")},
    ]

    dict_spec = parse_conda_spec("my-package-v2==0.1")
    assert dict_spec == [
        {"version": ("eq", "0.1"), "package_name": ("eq", "my-package-v2")},
    ]

    dict_spec = parse_conda_spec("my-package>=0.1.2,<0.2")
    assert dict_spec == [
        {
            "version": ("and", ("gte", "0.1.2"), ("lt", "0.2")),
            "package_name": ("eq", "my-package"),
        },
    ]

    dict_spec = parse_conda_spec("my-package>=0.1.2,<0.2,other-package==1.1")
    assert dict_spec == [
        {
            "version": ("and", ("gte", "0.1.2"), ("lt", "0.2")),
            "package_name": ("eq", "my-package"),
        },
        {
            "version": ("eq", "1.1"),
            "package_name": ("eq", "other-package"),
        },
    ]

    dict_spec = parse_conda_spec("my-package")
    assert dict_spec == [{"package_name": ("eq", "my-package")}]


@pytest.mark.parametrize(
    "spec,n_tasks",
    [
        ("my-package==0.1", 1),
        ("my-package==0.2", 0),
        ("my-package==0.1,my-package==0.2", 1),
        ("my-package", 1),
    ],
)
def test_filter_versions(config, db, user, package_version, spec, n_tasks):

    func_serialized = pickle.dumps(func)
    job = Job(
        owner_id=user.id,
        manifest=func_serialized,
        items_spec=spec,
    )
    manager = SubprocessWorker("", {}, config)
    db.add(job)
    db.commit()
    run_jobs(db)
    run_tasks(db, manager)
    db.refresh(job)
    n_created_tasks = db.query(Task).count()

    assert n_created_tasks == n_tasks
