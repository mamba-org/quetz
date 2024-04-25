import subprocess
from pathlib import Path

import quetz
from quetz.utils import add_entry_for_index


@quetz.hookimpl
def post_package_indexing(tempdir: Path, channel_name, subdirs, files, packages):
    for subdir in subdirs:
        path1 = tempdir / channel_name / subdir / "repodata.json"
        path2 = tempdir / channel_name / subdir / "repodata.json.zck"

        try:
            subprocess.check_call(["zck", path1, "-o", path2])
        except FileNotFoundError:
            raise RuntimeError(
                "zchunk does not seem to be installed, "
                "you can install it with:\n"
                "mamba install zchunk -c conda-forge"
            )
        except subprocess.CalledProcessError:
            raise RuntimeError("Error calling zck on repodata.")

        with open(path2, "rb") as fi:
            add_entry_for_index(files, subdir, "repodata.json.zck", fi.read())
