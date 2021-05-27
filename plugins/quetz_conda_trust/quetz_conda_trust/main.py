from pathlib import Path

import quetz
from quetz.utils import add_temp_static_file

from .api import router
from .repo_signer import RepoSigner


@quetz.hookimpl
def register_router():
    return router


@quetz.hookimpl
def post_package_indexing(tempdir: Path, channel_name, subdirs, files, packages):
    for subdir in subdirs:
        repodata_folderpath = tempdir / channel_name / subdir

        RepoSigner(repodata_folderpath)

        with open(tempdir / channel_name / subdir / "repodata_signed.json") as f:
            repodata_signed = f.read()

        add_temp_static_file(
            repodata_signed,
            channel_name,
            subdir,
            "repodata_signed.json",
            tempdir,
            files,
        )
