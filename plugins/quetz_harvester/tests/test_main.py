from pathlib import Path

import pytest
from httpx import AsyncClient

from quetz.db_models import PackageVersion
from quetz.jobs.models import Job, Task, TaskStatus
from quetz.jobs.runner import check_status, run_jobs, run_tasks


@pytest.mark.asyncio
async def test_harvest_endpoint_and_job(
    auth_client, db, config, work_manager, package_version, app, channel_name
):

    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.put("/api/harvester", json={"package_spec": "*"})

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
        Path("metadata")
        / package_version.platform
        / package_version.filename.replace(".tar.bz2", ".json"),
    )
    ok_ = fileh.read(10)
    assert ok_

    # cleanup
    try:
        db.query(PackageVersion).delete()
        db.query(Job).delete()
        db.query(Task).delete()
    finally:
        db.commit()
