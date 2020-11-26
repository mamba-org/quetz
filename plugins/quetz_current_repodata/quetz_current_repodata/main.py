import bz2
import hashlib
import json
from datetime import datetime, timezone

from conda_build.index import _build_current_repodata
from fastapi import APIRouter

import quetz

router = APIRouter()


@quetz.hookimpl
def register_router():
    return router


@quetz.hookimpl
def post_package_indexing(
    pkgstore: "quetz.pkgstores.PackageStore", channel_name, subdirs, files
):
    fname = "current_repodata.json"
    pins = {}
    for subdir in subdirs:
        updated_files = []

        path = f"{subdir}/{fname}"
        f = pkgstore.serve_path(channel_name, f"{subdir}/repodata.json")
        repodata = json.load(f)

        current_repodata = _build_current_repodata(subdir, repodata, pins)

        raw_current_repodata = json.dumps(
            current_repodata, indent=2, sort_keys=True
        ).encode("utf-8")
        compressed_current_repodata = bz2.compress(raw_current_repodata)

        pkgstore.add_file(raw_current_repodata, channel_name, path)
        pkgstore.add_file(compressed_current_repodata, channel_name, path + ".bz2")

        updated_files.append((fname, raw_current_repodata))
        updated_files.append((fname + ".bz2", compressed_current_repodata))

        update_index(pkgstore, updated_files, channel_name, subdir, files)


def update_index(pkgstore, updated_files, channel_name, subdir, files):
    for fname, data in updated_files:
        md5 = hashlib.md5()
        sha = hashlib.sha256()
        if not isinstance(data, bytes):
            data_bytes = data.encode("utf-8")
        else:
            data_bytes = data
        md5.update(data_bytes)
        sha.update(data_bytes)

        files[subdir].append(
            {
                "name": f"{fname}",
                "size": len(data_bytes),
                "timestamp": datetime.now(timezone.utc),
                "md5": md5.hexdigest(),
                "sha256": sha.hexdigest(),
            }
        )
