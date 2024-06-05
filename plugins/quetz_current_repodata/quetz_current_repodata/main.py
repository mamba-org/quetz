import json
from pathlib import Path

from conda_index.index import _build_current_repodata

import quetz
from quetz.config import Config
from quetz.utils import add_temp_static_file

config = Config()
compression = config.get_compression_config()


@quetz.hookimpl
def post_package_indexing(tempdir: Path, channel_name, subdirs, files, packages):
    pins = {}
    for subdir in subdirs:
        with open(tempdir / channel_name / subdir / "repodata.json") as f:
            repodata = json.load(f)

        current_repodata = _build_current_repodata(subdir, repodata, pins)

        current_repodata_string = json.dumps(current_repodata, indent=2, sort_keys=True)

        add_temp_static_file(
            current_repodata_string,
            channel_name,
            subdir,
            "current_repodata.json",
            tempdir,
            files,
            compression,
        )
