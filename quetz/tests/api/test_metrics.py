from datetime import datetime

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
