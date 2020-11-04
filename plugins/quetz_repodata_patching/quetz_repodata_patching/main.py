import bz2
import json
import tarfile
from contextlib import contextmanager

import quetz
from quetz.db_models import PackageVersion
from quetz.deps import get_db


def patch_repodata(repodata, patches):
    packages = repodata["packages"]
    # patch packages
    for pkg, info in patches["packages"].items():
        packages[pkg].update(info)

    # revoke packages
    for revoked_pkg_name in patches["revoke"]:
        if revoked_pkg_name not in packages:
            continue
        package = packages[revoked_pkg_name]
        package['revoked'] = True
        package["depends"].append('package_has_been_revoked')


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

                for fname in ("repodata", "current_repodata"):
                    fs = pkgstore.serve_path(channel_name, f"{subdir}/{fname}.json")

                    repodata_str = fs.read()
                    repodata = json.loads(repodata_str)

                    pkgstore.add_file(
                        repodata_str,
                        channel_name,
                        f"{subdir}/{fname}_from_packages.json",
                    )
                    compressed_repodata_str = bz2.compress(repodata_str)

                    pkgstore.add_file(
                        compressed_repodata_str,
                        channel_name,
                        f"{subdir}/{fname}_from_packages.json.bz2",
                    )

                    patch_repodata(repodata, patch_instructions)

                    patched_repodata_str = json.dumps(repodata)
                    compressed_patched_repodata_str = bz2.compress(
                        patched_repodata_str.encode('utf-8')
                    )

                    pkgstore.add_file(
                        patched_repodata_str, channel_name, f"{subdir}/{fname}.json"
                    )
                    pkgstore.add_file(
                        compressed_patched_repodata_str,
                        channel_name,
                        f"{subdir}/{fname}.json.bz2",
                    )
