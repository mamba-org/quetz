from pathlib import Path

import quetz
from quetz.utils import add_temp_static_file

from . import db_models
from .api import get_db_manager, router
from .repo_signer import RepoSigner


@quetz.hookimpl
def register_router():
    return router


@quetz.hookimpl
def post_package_indexing(tempdir: Path, channel_name, subdirs, files, packages):
    with get_db_manager() as db:
        query = (
            db.query(db_models.RepodataSigningKey)
            .filter(
                db_models.RepodataSigningKey.channel_name == channel_name,
            )
            .all()
        )

        if query:
            for each_key in query:
                for subdir in subdirs:
                    repodata_folderpath = tempdir / channel_name / subdir

                    RepoSigner(repodata_folderpath, each_key.private_key)

                    with open(tempdir / channel_name / subdir / "repodata.json") as f:
                        repodata_signed = f.read()

                    add_temp_static_file(
                        repodata_signed,
                        channel_name,
                        subdir,
                        "repodata.json",
                        tempdir,
                        files,
                    )
