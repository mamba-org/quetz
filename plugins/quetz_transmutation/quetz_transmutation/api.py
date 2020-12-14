import os
import pickle
from pathlib import Path
from tempfile import NamedTemporaryFile

from conda_package_handling.api import _convert
from fastapi import APIRouter, Depends

from quetz import authorization
from quetz.dao import Dao
from quetz.deps import get_db, get_rules
from quetz.jobs.models import Job
from quetz.pkgstores import PackageStore

from .rest_models import PackageSpec

router = APIRouter()


def transmutation(package_version: dict, config, pkgstore: PackageStore, dao: Dao):
    filename: str = package_version["filename"]
    channel: str = package_version["channel_name"]
    package_format: str = package_version["package_format"]
    package_name: str = package_version["package_name"]
    platform = package_version["platform"]
    version = package_version["version"]
    build_number = package_version["build_number"]
    build_string = package_version["build_string"]
    size = package_version["size"]
    uploader_id = package_version["uploader_id"]
    info = package_version["info"]

    if package_format == "tarbz2" or not filename.endswith(".tar.bz2"):
        return

    fh = pkgstore.serve_path(channel, Path(platform) / filename)

    with NamedTemporaryFile("wb", delete=False) as local_file:
        while fh_buffer := fh.read(100_000):
            local_file.write(fh_buffer)
    out_folder = os.path.basename(local_file.name)
    _convert(local_file.name, ".conda", out_folder)
    out_file = local_file.name.replace(".tar.bz2", ".conda")
    filename_conda = filename.replace(".tar.bz2", ".conda")
    version = dao.create_version(
        channel,
        package_name,
        "conda",
        platform,
        version,
        build_number,
        build_string,
        filename_conda,
        info,
        uploader_id,
        size,
    )
    pkgstore.add_file(out_file, channel, Path(platform) / filename_conda)


transmutation_serialized = pickle.dumps(transmutation)


@router.put("/api/transmutation")
def put_transmutation(
    package_spec: PackageSpec,
    db=Depends(get_db),
    auth: authorization.Rules = Depends(get_rules),
):
    user = auth.get_user()
    job = Job(
        owner_id=user,
        manifest=transmutation_serialized,
        items_spec=package_spec.package_spec,
    )
    db.add(job)
    db.commit()
