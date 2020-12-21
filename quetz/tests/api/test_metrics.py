from datetime import datetime

import pytest

from quetz.dao import Dao
from quetz.metrics.db_models import IntervalType, round_timestamp


def test_round_timestamp():
    timestamp = datetime.fromisoformat("2020-02-03T04:05")
    rounded = datetime.fromisoformat("2020-02-03T00:00")
    period = IntervalType.day
    assert round_timestamp(timestamp, period) == rounded

    period = IntervalType.hour
    rounded = datetime(2020, 2, 3, 4, 00)
    assert round_timestamp(timestamp, period) == rounded


def test_get_download_count(auth_client, public_channel, package_version, db, dao: Dao):

    timestamps = [
        "2020-01-05T21:01",
        "2020-01-06T22:10",
        "2020-02-18T10:10",
    ]

    month_day = []
    for t in timestamps:
        dt = datetime.fromisoformat(t)
        dao.incr_download_count(
            public_channel.name,
            package_version.filename,
            package_version.platform,
            timestamp=dt,
        )
        month_day.append((dt.month, dt.day))

    endpoint_url = (
        f"/metrics/channels/{public_channel.name}/"
        f"packages/{package_version.package_name}/"
        f"versions/{package_version.platform}/{package_version.filename}"
    )

    response = auth_client.get(endpoint_url)
    assert response.status_code == 200

    assert response.json() == {
        "period": "D",
        "metric_name": "download",
        "total": 3,
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
        "total": 2,
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
        "total": 3,
        "series": [
            {"timestamp": f"2020-{m:02}-01T00:00:00", "count": c}
            for m, c in [(1, 2), (2, 1)]
        ],
    }


@pytest.fixture
def package_version_factory(channel_name, user, dao):

    package_format = "tarbz2"
    package_info = "{}"

    def factory(package_name, version, build_str=0, platform="linux-64"):

        filename = f"{package_name}-{version}-{build_str}.tar.bz2"

        version = dao.create_version(
            channel_name,
            package_name,
            package_format,
            "linux-64",
            version,
            build_str,
            str(build_str),
            str(filename),
            package_info,
            user.id,
            size=11,
        )
        return version

    return factory


def test_get_channel_download_count(
    auth_client, public_channel, package_version_factory, db, dao: Dao
):

    versions = [package_version_factory("test-package", str(i)) for i in range(3)]

    now = datetime.utcnow()

    for v in versions:
        dao.incr_download_count(
            public_channel.name,
            v.filename,
            v.platform,
            timestamp=now,
        )

    endpoint_url = f"/metrics/channels/{public_channel.name}"

    response = auth_client.get(endpoint_url)
    assert response.status_code == 200

    expected = {
        "metric_name": "download",
        "period": "D",
        "packages": {
            v.filename: {
                "series": [
                    {
                        "timestamp": now.replace(
                            minute=0, second=0, microsecond=0, hour=0
                        ).isoformat(),
                        "count": 1,
                    }
                ]
            }
            for v in versions
        },
    }

    assert response.json() == expected
