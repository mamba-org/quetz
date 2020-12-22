from datetime import datetime
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
        query_str = ["period=H"]
        if m.last_synchronised:
            query_str.append(f"start={m.last_synchronised.isoformat()}")
        parsed = parsed._replace(
            path=parsed.path.replace("api", "metrics"), query="&".join(query_str)
        )
        metrics_url = urlunparse(parsed)
        response = session.get(metrics_url)

        if response.status_code != 200:
            raise TaskError(
                f"mirror server {metrics_url} returned bad response with code "
                f"{response.status_code} and message {response.text}"
            )

        response_data = response.json()
        packages = response_data["packages"]

        for platform_filename, data in packages.items():
            platform, filename = platform_filename.split('/')
            for s in data["series"]:
                timestamp = datetime.fromisoformat(s["timestamp"])
                count = s["count"]
                dao.incr_download_count(
                    channel_name, filename, platform, timestamp, count
                )
        m.last_synchronised = datetime.fromisoformat(response_data['server_timestamp'])
        dao.db.commit()
