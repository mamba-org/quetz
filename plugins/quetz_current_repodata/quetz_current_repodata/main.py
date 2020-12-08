import json

from conda_build.index import _build_current_repodata

import quetz
from quetz.utils import add_static_file


@quetz.hookimpl
def post_package_indexing(
    pkgstore: "quetz.pkgstores.PackageStore", channel_name, subdirs, files, packages
):
    pins = {}
    for subdir in subdirs:
        f = pkgstore.serve_path(channel_name, f"{subdir}/repodata.json")
        repodata = json.load(f)

        current_repodata = _build_current_repodata(subdir, repodata, pins)

        add_static_file(
            current_repodata,
            channel_name,
            subdir,
            "current_repodata.json",
            pkgstore,
            files,
        )
