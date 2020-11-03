import json
import tarfile
from contextlib import contextmanager

import quetz
from quetz.db_models import PackageVersion
from quetz.deps import get_db


@quetz.hookimpl
def post_package_indexing(
    pkgstore: "quetz.pkgstores.PackageStore", channel_name, subdirs
):

    get_db_manager = contextmanager(get_db)
    with get_db_manager() as db:

        query = (
            db.query(PackageVersion)
            .filter(
                PackageVersion.channel_name == channel_name,
                PackageVersion.package_name == f"{channel_name}-repodata-patches",
            )
            .order_by(PackageVersion.version.desc())
        )
        patches_pkg = query.one_or_none()

    if patches_pkg:
        fs = pkgstore.serve_path(channel_name, "noarch/" + patches_pkg.filename)

        with tarfile.open(mode='r:bz2', fileobj=fs) as patch_archive:
            for subdir in subdirs:
                patch_instructions = json.load(
                    patch_archive.extractfile(f"{subdir}/patch_instructions.json")
                )
                fs = pkgstore.serve_path(channel_name, f"{subdir}/repodata.json")

                repodata_str = fs.read()
                repodata = json.loads(repodata_str)

                pkgstore.add_file(
                    repodata_str, channel_name, f"{subdir}/repodata_from_packages.json"
                )

                for pkg, info in patch_instructions["packages"].items():
                    repodata["packages"][pkg].update(info)

                pkgstore.add_file(
                    json.dumps(repodata), channel_name, f"{subdir}/repodata.json"
                )
