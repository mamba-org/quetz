import json
import logging
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from conda_package_handling.api import _convert

from quetz.condainfo import calculate_file_hashes_and_size
from quetz.dao import Dao
from quetz.pkgstores import PackageStore

logger = logging.getLogger("quetz.plugins")


def transmutation(package_version: dict, config, pkgstore: PackageStore, dao: Dao):
    filename: str = package_version["filename"]
    channel: str = package_version["channel_name"]
    package_format: str = package_version["package_format"]
    package_name: str = package_version["package_name"]
    platform = package_version["platform"]
    version = package_version["version"]
    build_number = package_version["build_number"]
    build_string = package_version["build_string"]
    uploader_id = package_version["uploader_id"]
    info = json.loads(package_version["info"])

    if package_format == "tarbz2" or not filename.endswith(".tar.bz2"):
        return

    fh = pkgstore.serve_path(channel, Path(platform) / filename)

    with TemporaryDirectory() as tmpdirname:
        local_file_name = os.path.join(tmpdirname, filename)
        with open(local_file_name, "wb") as local_file:
            # chunk size 10MB
            shutil.copyfileobj(fh, local_file, 10 * 1024 * 1024)

        fn, out_fn, errors = _convert(local_file_name, ".conda", tmpdirname, force=True)

        if errors:
            logger.error(f"transmutation errors --> {errors}")
            return

        filename_conda = os.path.basename(filename).replace('.tar.bz2', '.conda')

        logger.info(f"Adding file to package store: {Path(platform) / filename_conda}")

        with open(out_fn, 'rb') as f:
            calculate_file_hashes_and_size(info, f)
            f.seek(0)
            pkgstore.add_package(f, channel, str(Path(platform) / filename_conda))

        version = dao.create_version(
            channel,
            package_name,
            "conda",
            platform,
            version,
            build_number,
            build_string,
            filename_conda,
            json.dumps(info),
            uploader_id,
            info["size"],
            upsert=True,
        )

        if os.path.exists(out_fn):
            os.remove(out_fn)
