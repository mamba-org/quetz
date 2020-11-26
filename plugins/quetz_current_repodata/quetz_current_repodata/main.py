import bz2
import json

from conda_build.index import _build_current_repodata

import quetz
from quetz.utils import add_entry_for_index


@quetz.hookimpl
def post_package_indexing(
    pkgstore: "quetz.pkgstores.PackageStore", channel_name, subdirs, files, packages
):
    fname = "current_repodata.json"
    pins = {}
    for subdir in subdirs:
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

        add_entry_for_index(files, subdir, fname, raw_current_repodata)
        add_entry_for_index(files, subdir, f"{fname}.bz2", compressed_current_repodata)
