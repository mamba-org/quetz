from pathlib import Path

import pytest
from httpx import AsyncClient

from quetz.db_models import PackageVersion
from quetz.jobs.models import Job, Task, TaskStatus
from quetz.jobs.runner import check_status, run_jobs, run_tasks


@pytest.mark.asyncio
async def test_transmutation_endpoint(
    auth_client, db, config, work_manager, package_version, app, channel_name
):

    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.put("/api/transmutation", json={})

    assert response.status_code == 200
    run_jobs(db)
    new_jobs = run_tasks(db, work_manager)
    await new_jobs[0].wait()

    check_status(db)

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
        .filter(PackageVersion.package_format == 'conda')
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
    ],
)
def test_package_specs(
    auth_client, db, config, work_manager, package_version, spec, n_tasks
):

    response = auth_client.put("/api/transmutation", json={"package_spec": spec})

    assert response.status_code == 200
    run_jobs(db)
    run_tasks(db, work_manager)

    check_status(db)

    n_created_task = db.query(Task).count()

    assert n_created_task == n_tasks

    # cleanup
    try:
        db.query(PackageVersion).delete()
        db.query(Job).delete()
        db.query(Task).delete()
    finally:
        db.commit()
