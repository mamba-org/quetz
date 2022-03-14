import os
import pickle
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from quetz.config import Config
from quetz.dao import Dao
from quetz.db_models import User
from quetz.jobs.dao import JobsDao
from quetz.jobs.models import Job, JobStatus, Task, TaskStatus
from quetz.jobs.runner import Supervisor, mk_sql_expr, parse_conda_spec
from quetz.rest_models import Channel, Package
from quetz.tasks.workers import SubprocessWorker
from quetz.testing.mockups import MockWorker

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def auto_rollback():
    return False


@pytest.fixture
def sqlite_in_memory():
    return False


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

    return package


@pytest.fixture
def manager(config, db):

    manager = SubprocessWorker(config)
    yield manager
    manager._executor.shutdown()
    SubprocessWorker._executor = None
    db.query(Job).delete()
    db.commit()


@pytest.fixture
def supervisor(db, config, manager):
    supervisor = Supervisor(db, manager)
    return supervisor


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
    time.sleep(0.25)


def dummy_func(package_version: dict):
    pass


@pytest.mark.asyncio
async def test_create_job(db, user, package_version, supervisor):

    func_serialized = pickle.dumps(func)
    job = Job(owner_id=user.id, manifest=func_serialized, items_spec="*")
    db.add(job)
    db.commit()
    supervisor.run_jobs()
    new_jobs = supervisor.run_tasks()
    db.refresh(job)
    task = db.query(Task).one()

    assert job.status == JobStatus.running

    assert task.status == TaskStatus.pending

    # wait for job to finish
    await new_jobs[0].wait()

    supervisor.check_status()

    db.refresh(task)
    assert task.status == TaskStatus.success
    assert os.path.isfile("test-output.txt")

    db.refresh(job)
    assert job.status == JobStatus.success


@pytest.mark.asyncio
async def test_run_tasks_only_on_new_versions(
    db, user, package_version, dao, channel_name, package_name, supervisor
):

    func_serialized = pickle.dumps(dummy_func)
    job = Job(owner_id=user.id, manifest=func_serialized, items_spec="*")
    db.add(job)
    db.commit()
    supervisor.run_jobs()
    new_jobs = supervisor.run_tasks()
    db.refresh(job)
    task = db.query(Task).one()

    await new_jobs[0].wait()
    supervisor.check_status()
    db.refresh(task)
    db.refresh(job)
    assert task.status == TaskStatus.success
    assert job.status == JobStatus.success

    job.status = JobStatus.pending
    db.commit()
    supervisor.run_jobs()
    new_jobs = supervisor.run_tasks()
    supervisor.check_status()
    db.refresh(job)
    assert not new_jobs
    assert job.status == JobStatus.success

    filename = "test-package-0.2-0.tar.bz2"
    add_package_version(filename, "0.2", channel_name, user, dao, package_name)

    job.status = JobStatus.pending
    db.commit()
    supervisor.run_jobs()
    new_jobs = supervisor.run_tasks()
    assert len(new_jobs) == 1
    assert job.status == JobStatus.running
    assert len(job.tasks) == 2
    assert job.tasks[0].status == TaskStatus.success
    assert job.tasks[1].status == TaskStatus.pending

    # force rerunning
    job.status = JobStatus.pending
    supervisor.run_jobs(force=True)
    db.refresh(job)
    new_jobs = supervisor.run_tasks()
    assert len(job.tasks) == 4
    assert len(new_jobs) == 2


@pytest.mark.asyncio
async def test_running_task(db, user, package_version, supervisor):

    func_serialized = pickle.dumps(long_running)
    job = Job(owner_id=user.id, manifest=func_serialized, items_spec="*")
    db.add(job)
    db.commit()
    supervisor.run_jobs()
    processes = supervisor.run_tasks()
    db.refresh(job)
    task = db.query(Task).one()

    assert job.status == JobStatus.running

    assert task.status == TaskStatus.pending

    # wait for task status to change
    for i in range(50):
        time.sleep(0.05)

        db.refresh(task)
        if task.status != TaskStatus.pending:
            break

    assert task.status == TaskStatus.running

    # wait for job to finish
    await processes[0].wait()

    supervisor.check_status()

    db.refresh(task)
    assert task.status == TaskStatus.success


@pytest.mark.parametrize("items_spec", [None, "*"])
@pytest.mark.asyncio
async def test_restart_worker_process(
    db, user, package_version, supervisor, caplog, items_spec
):
    # test if we can resume jobs if a worker was killed/restarted
    func_serialized = pickle.dumps(long_running)

    job = Job(owner_id=user.id, manifest=func_serialized, items_spec="*")
    db.add(job)
    db.commit()
    supervisor.run_jobs()
    supervisor.run_tasks()
    db.refresh(job)
    task = db.query(Task).one()

    assert job.status == JobStatus.running

    assert task.status == TaskStatus.pending

    # wait for task status to change
    for i in range(50):
        time.sleep(0.05)

        db.refresh(task)
        if task.status != TaskStatus.pending:
            break

    db.refresh(task)
    assert task.status == TaskStatus.running

    # simulate restart
    supervisor = Supervisor(db, supervisor.manager)

    db.refresh(job)
    assert job.status == JobStatus.running
    assert task.status == TaskStatus.failed
    assert "failed" in caplog.text

    supervisor.run_once()

    db.refresh(job)

    assert job.status == JobStatus.failed


@pytest.mark.asyncio
async def test_failed_task(db, user, package_version, supervisor):

    func_serialized = pickle.dumps(failed_func)
    job = Job(owner_id=user.id, manifest=func_serialized, items_spec="*")
    db.add(job)
    db.commit()
    supervisor.run_jobs()
    new_jobs = supervisor.run_tasks()
    task = db.query(Task).one()
    with pytest.raises(Exception, match="some exception"):
        await new_jobs[0].wait()

    supervisor.check_status()

    db.refresh(task)
    assert task.status == TaskStatus.failed

    db.refresh(job)
    assert job.status == JobStatus.failed


@pytest.mark.parametrize("items_spec", [""])
def test_empty_package_spec(db, user, package_version, caplog, items_spec, supervisor):

    func_serialized = pickle.dumps(func)
    job = Job(owner_id=user.id, manifest=func_serialized, items_spec=items_spec)
    db.add(job)
    db.commit()
    supervisor.run_jobs()
    db.refresh(job)
    task = db.query(Task).one_or_none()

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

    spec = [{"package_name": ("like", "*")}]
    sql_expr = compile(spec)

    assert sql_expr == ("lower(package_versions.package_name) LIKE lower('%')")


def test_parse_conda_spec():
    dict_spec = parse_conda_spec("*")
    assert dict_spec == [{"package_name": ("like", "*")}]

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
def test_filter_versions(db, user, package_version, spec, n_tasks, supervisor):

    func_serialized = pickle.dumps(func)
    job = Job(
        owner_id=user.id,
        manifest=func_serialized,
        items_spec=spec,
    )
    db.add(job)
    db.commit()
    supervisor.run_jobs()
    supervisor.run_tasks()
    db.refresh(job)
    n_created_tasks = db.query(Task).count()

    assert n_created_tasks == n_tasks


@pytest.mark.parametrize("user_role", ["owner"])
def test_refresh_job(auth_client, user, db, package_version, supervisor):

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

    supervisor.run_jobs()
    supervisor.check_status()
    assert job.status == JobStatus.success
    assert len(job.tasks) == 1

    response = auth_client.patch(
        f"/api/jobs/{job.id}", json={"status": "pending", "force": True}
    )
    supervisor.run_jobs()
    db.refresh(job)
    assert job.status == JobStatus.running
    assert len(job.tasks) == 2

    # forcing one job should not affect the other
    other_job = Job(
        id=2,
        owner_id=user.id,
        manifest=func_serialized,
        items_spec="*",
        status=JobStatus.success,
    )
    job.status = JobStatus.pending
    db.add(other_job)
    db.commit()

    response = auth_client.patch(
        f"/api/jobs/{other_job.id}", json={"status": "pending", "force": True}
    )
    db.refresh(job)
    assert job.status == JobStatus.pending
    assert len(job.tasks) == 2


@pytest.fixture(scope="session")
def dummy_job_plugin(test_data_dir):
    plugin_dir = str(Path(test_data_dir) / "dummy-plugin")
    sys.path.insert(0, plugin_dir)

    yield

    sys.path.remove(plugin_dir)


@pytest.mark.parametrize("user_role", ["owner"])
@pytest.mark.parametrize(
    "manifest",
    [
        "dummy_func",
        "os:listdir",
        "os.listdir",
        "quetz.dummy_func",
        "quetz-plugin:dummy_func",
        "quetz-dummyplugin:missing_job",
        "quetz-dummyplugin:dummy_job:error",
    ],
)
def test_post_new_job_manifest_validation(
    auth_client, user, db, manifest, dummy_job_plugin
):
    response = auth_client.post(
        "/api/jobs", json={"items_spec": "*", "manifest": manifest}
    )
    assert response.status_code == 422
    msg = response.json()['detail'][0]['msg']
    assert "invalid function" in msg
    for name in manifest.split(":"):
        assert name in msg


@pytest.mark.parametrize("user_role", ["owner"])
def test_post_new_job_invalid_items_spec(auth_client, user, db, dummy_job_plugin):
    # items_spec=None is not allowed for jobs
    # (but it works with actions)
    manifest = "quetz-dummyplugin:dummy_func"
    response = auth_client.post(
        "/api/jobs", json={"items_spec": None, "manifest": manifest}
    )
    assert response.status_code == 422
    msg = response.json()['detail']
    assert "not an allowed value" in msg[0]['msg']


@pytest.mark.parametrize("user_role", ["owner"])
@pytest.mark.parametrize(
    "manifest", ["quetz-dummyplugin:dummy_func", "quetz-dummyplugin:dummy_job"]
)
def test_post_new_job_from_plugin(
    auth_client,
    user,
    db,
    manifest,
    dummy_job_plugin,
    sync_supervisor,
    package_version,
    mocker,
):
    dummy_func = mocker.Mock()
    mocker.patch("quetz_dummyplugin.jobs.dummy_func", dummy_func, create=True)
    response = auth_client.post(
        "/api/jobs", json={"items_spec": "*", "manifest": manifest}
    )
    assert response.status_code == 201
    job_id = response.json()['id']
    job = db.query(Job).get(job_id)
    assert job.manifest.decode('ascii') == manifest

    sync_supervisor.run_once()

    assert job.status == JobStatus.success
    assert job.tasks

    if manifest.endswith("dummy_func"):
        dummy_func.assert_called_once()
    else:
        dummy_func.assert_not_called()


@pytest.mark.parametrize("user_role", ["owner"])
def test_post_new_job_with_handler(
    auth_client, user, db, mock_action, sync_supervisor, package_version
):

    response = auth_client.post(
        "/api/jobs", json={"items_spec": "*", "manifest": "test_action"}
    )
    assert response.status_code == 201
    job_id = response.json()['id']
    job = db.query(Job).get(job_id)
    assert job.status == JobStatus.pending
    assert job.manifest.decode('ascii') == "test_action"

    sync_supervisor.run_once()

    assert job.status == JobStatus.success
    assert job.tasks

    mock_action.assert_called_once()


@pytest.mark.parametrize("user_role", ["owner"])
@pytest.mark.parametrize(
    "status,job_ids",
    [
        (["pending"], [1]),
        (["running"], [0]),
        (["pending", "running"], [0, 1]),
        ([], [0, 1]),
        (["success"], []),
    ],
)
def test_filter_jobs_by_status(auth_client, db, user, status, job_ids):
    job0 = Job(
        id=0,
        items_spec="*",
        manifest=b"dummy_func",
        status=JobStatus.running,
        owner=user,
    )
    db.add(job0)
    job1 = Job(
        id=1,
        items_spec="*",
        manifest=b"dummy_func",
        status=JobStatus.pending,
        owner=user,
    )
    db.add(job1)

    db.commit()

    query = "&".join(["status={}".format(s) for s in status])

    response = auth_client.get(f"/api/jobs?{query}")

    assert response.status_code == 200
    response_data = response.json()
    assert {job['id'] for job in response_data['result']} == set(job_ids)
    assert response_data['pagination']['all_records_count'] == len(job_ids)


@pytest.mark.parametrize("user_role", ["owner"])
@pytest.mark.parametrize(
    "query_str,ok",
    [
        ("status=pending&status=running", True),
        ("status=missing", False),
        ("status=success", True),
        ("status=failed", True),
        ("status=pending,running", False),
        ("limit=wrongtype", False),
        ("limit=10", True),
    ],
)
def test_validate_query_string(auth_client, query_str, ok):
    response = auth_client.get(f"/api/jobs?{query_str}")
    if ok:
        assert response.status_code == 200
    else:
        assert response.status_code == 422


@pytest.fixture
def many_jobs(db, user):

    n_jobs = 5
    jobs = []
    for i in range(n_jobs):
        job = Job(
            id=i,
            items_spec="*",
            manifest=b"dummy_func",
            status=JobStatus.running,
            owner=user,
        )
        db.add(job)
        jobs.append(job)

    yield jobs

    for job in jobs:
        db.delete(job)
    db.commit()


@pytest.mark.parametrize("user_role", ["owner"])
@pytest.mark.parametrize("skip,limit", [(0, 2), (1, -1), (2, 1), (2, 5)])
def test_jobs_pagination(auth_client, skip, limit, many_jobs):

    n_jobs = len(many_jobs)

    response = auth_client.get(f"/api/jobs?skip={skip}&limit={limit}")
    assert response.status_code == 200

    jobs = response.json()["result"]

    assert jobs[0]['id'] == skip
    if limit > 0:
        assert jobs[-1]['id'] == min(n_jobs - 1, skip + limit - 1)
        assert len(jobs) == min(n_jobs - skip, limit)
    else:
        assert jobs[-1]['id'] == n_jobs - 1


@pytest.mark.parametrize(
    "query_params,expected_task_count",
    [
        ("", 1),
        ("status=created&status=pending", 1),
        ("skip=0&limit=1", 1),
        ("skip=1", 0),
        ("limit=0", 0),
        ("status=running", 0),
    ],
)
@pytest.mark.parametrize("user_role", ["owner"])
def test_get_tasks(
    auth_client, db, user, package_version, query_params, expected_task_count
):
    job = Job(items_spec="*", owner=user, manifest=pickle.dumps(dummy_func))
    db.add(job)
    task = Task(job=job, package_version=package_version)
    db.add(task)

    db.commit()

    response = auth_client.get(f"/api/jobs/{job.id}/tasks?{query_params}")
    assert response.status_code == 200
    data = response.json()

    assert len(data['result']) == expected_task_count

    if expected_task_count > 0:
        assert data['result'][0]['id'] == task.id
        assert data['result'][0]['job_id'] == job.id


@pytest.fixture()
def other_user(db):

    other_user = User(id=uuid.uuid4().bytes, username='otheruser')

    db.add(other_user)

    yield other_user

    db.delete(other_user)
    db.commit()


@pytest.mark.parametrize("user_role", ["member"])
def test_get_user_jobs(auth_client, db, user, package_version, other_user):
    job = Job(items_spec="*", owner=user, manifest=b"dummy_func")
    db.add(job)

    other_job = Job(items_spec="*", owner=other_user, manifest=b"dummy_func")
    db.add(other_job)

    db.commit()

    response = auth_client.get("/api/jobs")
    assert response.status_code == 200
    data = response.json()['result']
    assert len(data) == 1


@pytest.fixture
def action_job(db, user):
    job_dao = JobsDao(db)
    job = job_dao.create_job(b"test_action", user.id, extra_args={"my_arg": 1})

    yield job

    db.delete(job)
    db.commit()


@pytest.fixture
def package_version_job(db, user, package_version):
    func_serialized = pickle.dumps(dummy_func)
    job = Job(owner=user, manifest=func_serialized, items_spec="*")
    db.add(job)
    db.commit()
    yield job

    db.delete(job)
    db.commit()


@pytest.fixture
def sync_supervisor(db, dao, config):
    "supervisor with synchronous test worker"
    manager = MockWorker(config, db, dao)
    supervisor = Supervisor(db, manager)
    return supervisor


@pytest.fixture
def mock_action(mocker):
    func = mocker.Mock()
    mocker.patch("quetz.jobs.handlers.JOB_HANDLERS", {"test_action": func})
    return func


def test_update_job_status(sync_supervisor, db, action_job):
    running_task = Task(status=TaskStatus.running)
    finished_task = Task(status=TaskStatus.success)
    action_job.tasks.append(running_task)
    action_job.tasks.append(finished_task)
    action_job.status = JobStatus.running

    db.commit()

    sync_supervisor.run_once()

    db.refresh(action_job)
    db.refresh(running_task)
    db.refresh(finished_task)

    assert finished_task.status == TaskStatus.success
    assert running_task.status == TaskStatus.running
    assert action_job.status == JobStatus.running


def test_run_action_handler(sync_supervisor, db, caplog, action_job, mock_action):
    sync_supervisor.run_once()
    assert "ERROR" not in caplog.text
    mock_action.assert_called_with(my_arg=1)
    db.refresh(action_job)
    assert action_job.tasks[0].status == TaskStatus.success
    assert action_job.status == JobStatus.success


def test_update_periodic_action(sync_supervisor, db, action_job, mock_action):
    job = action_job
    job.repeat_every_seconds = 10
    db.commit()

    sync_supervisor.run_once()
    db.refresh(action_job)
    assert job.tasks[0].status == TaskStatus.success
    assert job.status == JobStatus.pending


@pytest.mark.parametrize("start_date", [datetime(1960, 1, 1, 10, 0, 0), None])
def test_run_action_once(sync_supervisor, db, action_job, mock_action, start_date):

    # job should start immediatedly
    action_job.start_at = start_date
    db.commit()

    assert action_job.status == JobStatus.pending

    sync_supervisor.run_once()

    db.refresh(action_job)

    assert len(action_job.tasks) == 1
    assert action_job.status == JobStatus.success

    sync_supervisor.run_once()

    db.refresh(action_job)
    assert len(action_job.tasks) == 1
    assert action_job.status == JobStatus.success


def test_run_action_after_delay(sync_supervisor, db, action_job, mock_action, mocker):

    action_job.start_at = datetime(3020, 1, 1, 10, 0)
    db.commit()

    assert action_job.status == JobStatus.pending

    sync_supervisor.run_once()

    db.refresh(action_job)

    assert len(action_job.tasks) == 0
    assert action_job.status == JobStatus.pending

    sync_supervisor.run_once()

    mock_datetime = mocker.patch("quetz.jobs.runner.datetime")
    mock_datetime.utcnow.return_value = datetime(3020, 1, 1, 10, 1)

    sync_supervisor.run_once()
    assert len(action_job.tasks) == 1
    assert action_job.status == JobStatus.success


@pytest.mark.parametrize("start_date", [datetime(1960, 1, 1, 10, 0, 0), None])
def test_run_periodic_action(
    sync_supervisor, db, action_job, mock_action, mocker, start_date
):

    action_job.repeat_every_seconds = 10
    action_job.start_date = start_date
    now = datetime.utcnow()
    delta = timedelta(seconds=11)

    db.commit()

    sync_supervisor.run_once()

    assert len(action_job.tasks) == 1
    assert action_job.status == JobStatus.pending

    sync_supervisor.run_once()

    assert len(action_job.tasks) == 1
    assert action_job.status == JobStatus.pending

    mock_datetime = mocker.patch("quetz.jobs.runner.datetime")
    mock_datetime.utcnow.return_value = now + delta

    sync_supervisor.run_once()
    assert len(action_job.tasks) == 2
    assert action_job.status == JobStatus.pending

    sync_supervisor.run_once()
    assert len(action_job.tasks) == 2
    assert action_job.status == JobStatus.pending


@pytest.mark.parametrize("start_date", [datetime(1960, 1, 1, 10, 0, 0), None])
def test_run_periodic_package_version_job(
    sync_supervisor, db, package_version_job, mocker, start_date
):
    package_version_job.repeat_every_seconds = 10
    package_version_job.start_date = start_date

    now = datetime.utcnow()
    delta = timedelta(seconds=11)

    db.commit()

    sync_supervisor.run_once()

    assert len(package_version_job.tasks) == 1
    assert package_version_job.tasks[0].status == TaskStatus.success
    assert package_version_job.status == JobStatus.pending

    sync_supervisor.run_once()
    assert len(package_version_job.tasks) == 1
    assert package_version_job.tasks[0].status == TaskStatus.success
    assert package_version_job.status == JobStatus.pending

    mock_datetime = mocker.patch("quetz.jobs.runner.datetime")
    mock_datetime.utcnow.return_value = now + delta

    sync_supervisor.run_once()
    assert len(package_version_job.tasks) == 2
    assert package_version_job.status == JobStatus.pending

    sync_supervisor.run_once()
    assert len(package_version_job.tasks) == 2
    assert package_version_job.status == JobStatus.pending
