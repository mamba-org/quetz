import json
from pathlib import Path
from typing import Optional

from libcflib.harvester import harvest as libc_harvest
from pydantic import BaseModel, Field

from quetz.dao import Dao
from quetz.pkgstores import PackageStore


class PackageSpec(BaseModel):
    package_spec: Optional[str] = Field(None, title="package version specification")


def harvest(package_version: dict, config, pkgstore: PackageStore, dao: Dao):
    filename: str = package_version["filename"]
    channel: str = package_version["channel_name"]
    platform = package_version["platform"]

    print(f"Harvesting: {filename}, {channel}, {platform}")
    # TODO figure out how to handle properly either .conda or .tar.bz2
    if not filename.endswith('.tar.bz2'):
        return

    fh = pkgstore.serve_path(channel, Path(platform) / filename)

    print("Harvesting ... ")
    try:
        result = libc_harvest(fh)
    except Exception as e:
        print(f"Exception caught in harvesting: {str(e)}")
        return

    print(f"Uploading harvest result for {channel}/{platform}/{filename}")

    pkgstore.add_file(
        json.dumps(result, indent=4, sort_keys=True),
        channel,
        Path("metadata") / platform / filename.replace('.tar.bz2', '.json'),
    )
