from pathlib import Path

import pytest
from httpx import AsyncClient

from quetz.db_models import PackageVersion
from quetz.jobs.models import Job, Task, TaskStatus


@pytest.mark.asyncio
async def test_harvest_endpoint_and_job(
    auth_client, db, config, supervisor, package_version, app, channel_name
):

    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.put("/api/harvester", json={"package_spec": "*"})

    assert response.status_code == 200
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
