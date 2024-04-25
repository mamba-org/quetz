from pathlib import Path

import pytest
from httpx import AsyncClient

from quetz.authorization import (
    SERVER_MAINTAINER,
    SERVER_MEMBER,
    SERVER_OWNER,
    SERVER_USER,
)
from quetz.db_models import PackageVersion
from quetz.jobs.models import Job, JobStatus, Task, TaskStatus


@pytest.mark.asyncio
async def test_transmutation_endpoint(
    api_key, db, config, supervisor, package_version, app, channel_name
):
    # we need to use asynchronous http client because the test is async
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post(
            "/api/jobs",
            json={"items_spec": "*", "manifest": "quetz-transmutation:transmutation"},
            headers={"x-api-key": api_key.key, "content-type": "application/json"},
        )

    assert response.status_code == 201
    supervisor.run_jobs()
    new_jobs = supervisor.run_tasks()
    await new_jobs[0].wait()

    supervisor.check_status()

    task = db.query(Task).one()
    db.refresh(task)
    assert task.status == TaskStatus.success

    pkgstore = config.get_package_store()
    fileh = pkgstore.serve_path(
        channel_name,
        Path(package_version.platform)
        / package_version.filename.replace(".tar.bz2", ".conda"),
    )
    ok_ = fileh.read(10)
    assert ok_

    conda_version = (
        db.query(PackageVersion)
        .filter(PackageVersion.package_format == "conda")
        .one_or_none()
    )

    assert conda_version

    # cleanup
    try:
        db.query(PackageVersion).delete()
        db.query(Job).delete()
        db.query(Task).delete()
    finally:
        db.commit()


@pytest.mark.parametrize(
    "spec,n_tasks",
    [
        ("my-package==0.1", 1),
        ("my-package==0.2", 0),
        ("my-package==0.1,my-package==0.2", 1),
        ("", 0),
        ("*", 1),
    ],
)
def test_package_specs(
    auth_client, db, config, supervisor, package_version, spec, n_tasks
):
    response = auth_client.post(
        "/api/jobs",
        json={"items_spec": spec, "manifest": "quetz-transmutation:transmutation"},
    )

    assert response.status_code == 201

    job_id = response.json()["id"]

    job = db.query(Job).filter(Job.id == job_id).one()

    assert job.status == JobStatus.pending

    supervisor.run_jobs()

    if n_tasks:
        assert job.status == JobStatus.running
    else:
        assert job.status == JobStatus.success

    n_created_task = db.query(Task).count()
    assert n_created_task == n_tasks

    supervisor.run_tasks()

    supervisor.check_status()

    # cleanup
    try:
        db.query(PackageVersion).delete()
        db.query(Job).delete()
        db.query(Task).delete()
    finally:
        db.commit()


@pytest.mark.parametrize(
    "user_role,expected_status",
    [
        (SERVER_OWNER, 201),
        (SERVER_MAINTAINER, 201),
        (SERVER_USER, 401),
        (SERVER_MEMBER, 401),
    ],
)
def test_permissions(auth_client, db, expected_status):
    response = auth_client.post(
        "/api/jobs",
        json={"items_spec": "*", "manifest": "quetz-transmutation:transmutation"},
    )

    assert response.status_code == expected_status
