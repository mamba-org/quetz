import json
import pickle
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from quetz_harvester.harvest import harvest

from quetz import authorization
from quetz.dao import Dao
from quetz.deps import get_db, get_rules
from quetz.jobs.models import Job
from quetz.pkgstores import PackageStore

router = APIRouter()


class PackageSpec(BaseModel):
    package_spec: Optional[str] = Field(None, title="package version specification")


def quetz_harvest(package_version: dict, config, pkgstore: PackageStore, dao: Dao):
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
        result = harvest(fh)
    except Exception as e:
        print(f"Exception caught in harvesting: {str(e)}")
        return

    print(f"Uploading harvest result for {channel}/{platform}/{filename}")

    pkgstore.add_file(
        json.dumps(result, indent=4, sort_keys=True),
        channel,
        Path("metadata") / platform / filename.replace('.tar.bz2', '.json'),
    )


harvest_serialized = pickle.dumps(quetz_harvest)


@router.put("/api/harvester", tags=["plugins"])
def put_harvest(
    package_spec: PackageSpec,
    db=Depends(get_db),
    auth: authorization.Rules = Depends(get_rules),
):
    user = auth.get_user()
    job = Job(
        owner_id=user,
        manifest=harvest_serialized,
        items_spec=package_spec.package_spec,
    )
    db.add(job)
    db.commit()
