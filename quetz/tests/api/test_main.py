import datetime
from unittest.mock import ANY

import pytest

from quetz.dao import Dao
from quetz.metrics.db_models import IntervalType, PackageVersionMetric


def test_get_package_list(package_version, package_name, channel_name, client):

    response = client.get("/api/dummylogin/bartosz")
    response = client.get(
        f"/api/channels/{channel_name}/packages/{package_name}/versions"
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": ANY,
            "channel_name": "my-channel",
            "package_name": "my-package",
            "platform": "linux-64",
            "version": "0.1",
            "build_string": "",
            "build_number": 0,
            "filename": "test-package-0.1-0.tar.bz2",
            "info": {},
            "uploader": {"name": "Bartosz", "avatar_url": "http:///avatar"},
            "time_created": ANY,
        }
    ]


def test_package_version_list_by_date(
    package_version, package_name, channel_name, client
):

    now = datetime.datetime.utcnow()
    later = now + datetime.timedelta(minutes=1)
    earlier = now - datetime.timedelta(minutes=1)

    response = client.get("/api/dummylogin/bartosz")
    response = client.get(
        f"/api/channels/{channel_name}/packages/{package_name}/versions"
        "?time_created__ge=" + later.isoformat()
    )

    assert response.status_code == 200
    assert response.json() == []

    response = client.get(
        f"/api/channels/{channel_name}/packages/{package_name}/versions"
        "?time_created__ge=" + earlier.isoformat()
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.parametrize(
    "channel_role,expected_code",
    [("owner", 201), ("maintainer", 201), ("member", 403), (None, 403)],
)
def test_add_package_permissions(auth_client, public_channel, expected_code):

    response = auth_client.post(
        f"/api/channels/{public_channel.name}/packages",
        json={"name": "test-package", "summary": "none", "description": "none"},
    )

    assert response.status_code == expected_code


@pytest.mark.parametrize(
    "channel_role,expected_code",
    [("owner", 200), ("maintainer", 200), ("member", 403), (None, 403)],
)
def test_get_channel_members(auth_client, public_channel, expected_code):

    response = auth_client.get(f"/api/channels/{public_channel.name}/members")

    assert response.status_code == expected_code


def test_upload_wrong_file_type(auth_client, public_channel):
    files = {"files": ("my_package-0.1-0.tar.bz", "dfdf")}
    response = auth_client.post(
        f"/api/channels/{public_channel.name}/files/", files=files
    )
    assert response.status_code == 400
    assert "not a bzip2 file" in response.json()['detail']


def test_increment_download_count(auth_client, public_channel, package_version, db):

    response = auth_client.get(
        f"/channels/{public_channel.name}/linux-64/test-package-0.1-0.tar.bz2"
    )

    assert response.status_code == 200

    metrics = (
        db.query(PackageVersionMetric)
        .filter(PackageVersionMetric.package_version_id == package_version.id)
        .all()
    )

    assert len(metrics) > 1
    assert metrics[0].count == 1

    response = auth_client.get(
        f"/channels/{public_channel.name}/linux-64/test-package-0.1-0.tar.bz2"
    )

    assert response.status_code == 200

    metric = (
        db.query(PackageVersionMetric)
        .filter(PackageVersionMetric.package_version_id == package_version.id)
        .filter(PackageVersionMetric.period == IntervalType.total)
        .one()
    )

    assert metric.count == 2


def test_get_download_count(auth_client, public_channel, package_version, db, dao: Dao):

    timestamps = [
        "2020-01-05T21:01",
        "2020-01-06T22:10",
        "2020-02-18T10:10",
    ]

    month_day = []
    for t in timestamps:
        dt = datetime.datetime.fromisoformat(t)
        dao.incr_download_count(
            public_channel.name,
            package_version.filename,
            package_version.platform,
            timestamp=dt,
        )
        month_day.append((dt.month, dt.day))

    endpoint_url = (
        f"/api/channels/{public_channel.name}/packages/{package_version.package_name}/"
        f"versions/{package_version.platform}/{package_version.filename}/metrics"
    )

    response = auth_client.get(endpoint_url)
    assert response.status_code == 200

    assert response.json() == {
        "period": "D",
        "metric_name": "download",
        "series": [
            {"timestamp": f"2020-{m:02}-{d:02}T00:00:00", "count": 1}
            for m, d in month_day
        ],
    }

    response = auth_client.get(endpoint_url + "?start=2020-01-05T10:00")
    assert response.status_code == 200

    assert response.json() == {
        "period": "D",
        "metric_name": "download",
        "series": [
            {"timestamp": f"2020-{m:02}-{d:02}T00:00:00", "count": 1}
            for m, d in month_day[1:]
        ],
    }

    response = auth_client.get(endpoint_url + "?period=M")
    assert response.status_code == 200

    assert response.json() == {
        "period": "M",
        "metric_name": "download",
        "series": [
            {"timestamp": f"2020-{m:02}-01T00:00:00", "count": c}
            for m, c in [(1, 2), (2, 1)]
        ],
    }
