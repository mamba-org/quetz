import logging
from datetime import datetime
from typing import Optional

import requests

from quetz.dao import Dao


def synchronize_metrics_from_mirrors(
    channel_name: str,
    dao: Dao,
    session: requests.Session,
    now: datetime = datetime.utcnow(),
):
    logger = logging.getLogger("quetz")
    channel = dao.get_channel(channel_name)
    if not channel:
        return
    for m in channel.mirrors:
        if not m.metrics_endpoint:
            logger.warning(
                f"metrics endpoint not configured for mirror {m.url}."
                "Skipping metrics synchronisation"
            )
            continue
        query_str = ["period=H"]
        start_time: Optional[datetime]
        if m.last_synchronised:
            start_time = m.last_synchronised.replace(minute=0, second=0, microsecond=0)
            query_str.append(f"start={start_time.isoformat()}")
        else:
            start_time = None

        # exclude incomplete intervals (the current hour)
        end_time = now.replace(minute=0, second=0, microsecond=0)

        if start_time == end_time:
            logger.debug(f"metrics data for mirror {m.url} are up-to-date")
            continue

        query_str.append(f"end={end_time.isoformat()}")

        metrics_url = m.metrics_endpoint + "?" + "&".join(query_str)
        response = session.get(metrics_url)

        if response.status_code != 200:
            logger.error(
                f"mirror server {metrics_url} returned bad response with code "
                f"{response.status_code} and message {response.text}"
            )
            continue

        response_data = response.json()
        try:
            packages = response_data["packages"]
        except KeyError:
            logger.error(
                f"malfromated respose received from {metrics_url}: "
                "missing 'packages' key"
            )
            continue

        for platform_filename, data in packages.items():
            platform, filename = platform_filename.split('/')
            for s in data["series"]:
                timestamp = datetime.fromisoformat(s["timestamp"])
                count = s["count"]
                dao.incr_download_count(
                    channel_name, filename, platform, timestamp, count
                )
        logger.debug(f"synchronized metrics from {metrics_url}")
        m.last_synchronised = end_time
        dao.db.commit()
