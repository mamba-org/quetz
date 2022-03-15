import sys
from pathlib import Path

import pytest

from quetz.db_models import PackageVersion
from quetz.jobs.models import Job, Task, TaskStatus


@pytest.mark.skipif(
    sys.version_info >= (3, 10),
    reason="xonsh pinning used by libcflib not compatible with python 3.10",
)
def test_harvest_endpoint_and_job(
    api_key, auth_client, db, config, supervisor, package_version, app, channel_name
):

    response = auth_client.post(
        "/api/jobs", json={"items_spec": "*", "manifest": "quetz-harvester:harvest"}
    )

    assert response.status_code == 201
    supervisor.run_jobs()
    supervisor.run_tasks()

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
