from pathlib import Path

import quetz
from quetz.utils import add_temp_static_file

from .repo_signer import RepoSigner


@quetz.hookimpl
def post_package_indexing(tempdir: Path, channel_name, subdirs, files, packages):
    for subdir in subdirs:
        repodata_folderpath = tempdir / channel_name / subdir

        RepoSigner(repodata_folderpath)

        with open(tempdir / channel_name / "1.root.json") as f:
            root_json = f.read()

        with open(tempdir / channel_name / "key_mgr.json") as f:
            key_mgr = f.read()

        with open(tempdir / channel_name / subdir / "repodata_signed.json") as f:
            repodata_signed = f.read()

        add_temp_static_file(
            root_json,
            channel_name,
            subdir=None,
            fname="1.root.json",
            temp_dir=tempdir,
            file_index=files,
        )

        add_temp_static_file(
            key_mgr,
            channel_name,
            subdir=None,
            fname="key_mgr.json",
            temp_dir=tempdir,
            file_index=files,
        )

        add_temp_static_file(
            repodata_signed,
            channel_name,
            subdir,
            "repodata_signed.json",
            tempdir,
            files,
        )
