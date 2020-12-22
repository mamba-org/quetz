from urllib.parse import urlparse, urlunparse

import requests

from quetz.dao import Dao
from quetz.errors import TaskError


def synchronize_metrics_from_mirrors(
    channel_name: str,
    dao: Dao,
    session: requests.Session,
):
    channel = dao.get_channel(channel_name)
    for m in channel.mirrors:
        parsed = urlparse(m.url)
        parsed = parsed._replace(path='/metrics' + parsed.path, query="period=H")
        metrics_url = urlunparse(parsed)
        response = session.get(metrics_url)

        if response.status_code != 200:
            raise TaskError(
                f"mirror server {metrics_url} returned bad response with code "
                f"{response.status_code} and message {response.content}"
            )

        packages = response.json()["packages"]

        for platform_filename, data in packages:
            platform, filename = platform_filename.split('/')
            for s in data["series"]:
                timestamp = s["timestamp"]
                count = s["count"]
                dao.incr_download_count(
                    channel_name, filename, platform, timestamp, count
                )
