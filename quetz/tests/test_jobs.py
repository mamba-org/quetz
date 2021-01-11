import os
import pickle
import time
from pathlib import Path

import pytest

from quetz.config import Config
from quetz.dao import Dao
from quetz.jobs.models import Job, JobStatus, Task, TaskStatus
from quetz.jobs.runner import (
    _process_cache,
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


def add_package_version(
    filename, package_version, channel_name, user, dao, package_name=None
):

    if not package_name:
        package_name = "test-package"

    package_format = "tarbz2"
    package_info = "{}"
    path = Path(filename)
    version = dao.create_version(
        channel_name,
        package_name,
        package_format,
        "linux-64",
        package_version,
        0,
        "",
        path.name,
        package_info,
        user.id,
        size=11,
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

    filename = "test-package-0.1-0.tar.bz2"
    version = add_package_version(
        filename, "0.1", channel_name, user, dao, package_name
    )
    path = Path(filename)
    with open(path, "rb") as fid:
        pkgstore.add_file(fid.read(), channel_name, "linux-64" / path)

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


@pytest.fixture
def manager(config):

    manager = SubprocessWorker("", {}, config)
    return manager


def test_create_task(db, user, package_version):
    job = Job(owner_id=user.id, manifest=b"")
    task = Task(job=job)
    db.add(job)
    db.add(task)
    db.commit()


def func(package_version: dict, config: Config):
    with open("test-output.txt", "a") as fid:
        fid.write("ok")


def failed_func(package_version: dict):
    raise Exception("some exception")


def long_running(package_version: dict):
    time.sleep(0.1)


def dummy_func(package_version: dict):
    pass


@pytest.mark.asyncio
async def test_create_job(db, user, package_version, manager):

    func_serialized = pickle.dumps(func)
    job = Job(owner_id=user.id, manifest=func_serialized, items_spec="*")
    db.add(job)
    db.commit()
    run_jobs(db)
    new_jobs = run_tasks(db, manager)
    db.refresh(job)
    task = db.query(Task).one()

    assert job.status == JobStatus.running

    assert task.status == TaskStatus.pending

    # wait for job to finish
    await new_jobs[0].wait()

    check_status(db)

    db.refresh(task)
    assert task.status == TaskStatus.success
    assert os.path.isfile("test-output.txt")

    db.refresh(job)
    assert job.status == JobStatus.success


@pytest.mark.asyncio
async def test_run_tasks_only_on_new_versions(
    db, user, package_version, manager, dao, channel_name, package_name
):

    func_serialized = pickle.dumps(dummy_func)
    job = Job(owner_id=user.id, manifest=func_serialized, items_spec="*")
    db.add(job)
    db.commit()
    run_jobs(db)
    new_jobs = run_tasks(db, manager)
    db.refresh(job)
    task = db.query(Task).one()

    await new_jobs[0].wait()
    check_status(db)
    db.refresh(task)
    db.refresh(job)
    assert task.status == TaskStatus.success
    assert job.status == JobStatus.success

    job.status = JobStatus.pending
    db.commit()
    run_jobs(db)
    new_jobs = run_tasks(db, manager)
    check_status(db)
    db.refresh(job)
    assert not new_jobs
    assert job.status == JobStatus.success

    filename = "test-package-0.2-0.tar.bz2"
    add_package_version(filename, "0.2", channel_name, user, dao, package_name)

    job.status = JobStatus.pending
    db.commit()
    run_jobs(db)
    new_jobs = run_tasks(db, manager)
    assert len(new_jobs) == 1
    assert job.status == JobStatus.running
    assert len(job.tasks) == 2
    assert job.tasks[0].status == TaskStatus.success
    assert job.tasks[1].status == TaskStatus.pending

    # force rerunning
    job.status = JobStatus.pending
    run_jobs(db, force=True)
    db.refresh(job)
    new_jobs = run_tasks(db, manager)
    assert len(job.tasks) == 4
    assert len(new_jobs) == 2


@pytest.mark.asyncio
async def test_running_task(db, user, package_version, manager):

    func_serialized = pickle.dumps(long_running)
    job = Job(owner_id=user.id, manifest=func_serialized, items_spec="*")
    db.add(job)
    db.commit()
    run_jobs(db)
    processes = run_tasks(db, manager)
    db.refresh(job)
    task = db.query(Task).one()

    assert job.status == JobStatus.running

    assert task.status == TaskStatus.pending

    time.sleep(0.01)
    check_status(db)

    db.refresh(task)
    assert task.status == TaskStatus.running

    # wait for job to finish
    await processes[0].wait()

    check_status(db)

    db.refresh(task)
    assert task.status == TaskStatus.success


@pytest.mark.asyncio
async def test_restart_worker_process(db, user, package_version, manager, caplog):
    # test if we can resume jobs if a worker was killed/restarted
    func_serialized = pickle.dumps(long_running)

    job = Job(owner_id=user.id, manifest=func_serialized, items_spec="*")
    db.add(job)
    db.commit()
    run_jobs(db)
    run_tasks(db, manager)
    db.refresh(job)
    task = db.query(Task).one()

    assert job.status == JobStatus.running

    assert task.status == TaskStatus.pending

    time.sleep(0.01)
    check_status(db)

    db.refresh(task)
    assert task.status == TaskStatus.running

    _process_cache.clear()

    check_status(db)
    assert task.status == TaskStatus.created
    assert "lost" in caplog.text

    new_processes = run_tasks(db, manager)
    db.refresh(task)

    assert len(new_processes) == 1
    assert task.status == TaskStatus.pending

    more_processes = run_tasks(db, manager)
    await new_processes[0].wait()
    even_more_processes = run_tasks(db, manager)
    check_status(db)
    db.refresh(task)
    assert not more_processes
    assert not even_more_processes
    assert task.status == TaskStatus.success


@pytest.mark.asyncio
async def test_failed_task(db, user, package_version, manager):

    func_serialized = pickle.dumps(failed_func)
    job = Job(owner_id=user.id, manifest=func_serialized, items_spec="*")
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


@pytest.mark.parametrize("items_spec", ["", None])
def test_empty_package_spec(db, user, package_version, caplog, items_spec):

    func_serialized = pickle.dumps(func)
    job = Job(owner_id=user.id, manifest=func_serialized, items_spec=items_spec)
    db.add(job)
    db.commit()
    run_jobs(db)
    db.refresh(job)
    task = db.query(Task).one_or_none()

    assert "empty" in caplog.text
    assert "skipping" in caplog.text
    assert job.status == JobStatus.success
    assert task is None


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

    spec = [{"package_name": ("like", "my-*")}]
    sql_expr = compile(spec)

    assert sql_expr == ("lower(package_versions.package_name) LIKE lower('my-%')")


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

    dict_spec = parse_conda_spec("my-*")
    assert dict_spec == [{"package_name": ("like", "my-*")}]


@pytest.mark.parametrize(
    "spec,n_tasks",
    [
        ("my-package==0.1", 1),
        ("my-package==0.2", 0),
        ("my-package==0.1,my-package==0.2", 1),
        ("my-package", 1),
        ("*", 1),
    ],
)
def test_filter_versions(db, user, package_version, spec, n_tasks, manager):

    func_serialized = pickle.dumps(func)
    job = Job(
        owner_id=user.id,
        manifest=func_serialized,
        items_spec=spec,
    )
    db.add(job)
    db.commit()
    run_jobs(db)
    run_tasks(db, manager)
    db.refresh(job)
    n_created_tasks = db.query(Task).count()

    assert n_created_tasks == n_tasks


@pytest.mark.parametrize("user_role", ["owner"])
def test_refresh_job(auth_client, user, db, package_version, manager):

    func_serialized = pickle.dumps(dummy_func)
    job = Job(
        owner_id=user.id,
        manifest=func_serialized,
        items_spec="*",
        status=JobStatus.success,
    )
    task = Task(job=job, status=TaskStatus.success, package_version=package_version)
    db.add(job)
    db.add(task)
    db.commit()

    assert job.status == JobStatus.success
    assert len(job.tasks) == 1

    response = auth_client.patch(f"/api/jobs/{job.id}", json={"status": "pending"})

    assert response.status_code == 200

    db.refresh(job)
    assert job.status == JobStatus.pending
    assert len(job.tasks) == 1

    run_jobs(db)
    assert job.status == JobStatus.success
    assert len(job.tasks) == 1

    response = auth_client.patch(
        f"/api/jobs/{job.id}", json={"status": "pending", "force": True}
    )
    db.refresh(job)
    assert job.status == JobStatus.running
    assert len(job.tasks) == 2


@pytest.mark.parametrize("user_role", ["owner"])
@pytest.mark.parametrize(
    "manifest", ["dummy_func", "quetz.dummy_func", "quetz-plugin:dummy_func"]
)
def test_post_new_job_manifest_validation(auth_client, user, db, manifest):
    response = auth_client.post(
        "/api/jobs", json={"items_spec": "*", "manifest": manifest}
    )
    assert response.status_code == 422
    assert "invalid function" in response.json()['detail']
