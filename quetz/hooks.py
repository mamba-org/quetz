from pathlib import Path
from typing import BinaryIO, List, Optional

import fastapi
import pluggy

import quetz
from quetz.condainfo import CondaInfo

hookspec = pluggy.HookspecMarker("quetz")


@hookspec
def post_add_package_version(
    version: 'quetz.db_models.PackageVersion', condainfo: 'quetz.condainfo.CondaInfo'
) -> None:
    """hook for post-processsing after adding a package file.

    :param quetz.db_models.PackageVersion version:
        package version model that was added in to the database

    :param quetz.condainfo.CondaInfo condainfo:
        metadata extracted from the archive

    """


@hookspec
def post_package_indexing(
    tempdir: Path,
    channel_name: str,
    subdirs: List[str],
    files: dict,
    packages: dict,
) -> None:
    """hook for post-processsing after building indexes.

    :param quetz.pkgstores.PackageStore pkgstore:
        package store used to store/retrieve packages

    :param str channel_name:
        metadata extracted from the archive

    :param list subdirs:
        list of subdirs with indexes

    :param dict files:
        a dict that contains list of files for each subdir
        - used in updating the index

    :param dict packages:
        a dict that contains list of packages for each subdir
        - used in updating the index
    """
    pass


@hookspec
def validate_new_package(
    channel_name: str,
    package_name: str,
    file_handler: Optional[BinaryIO],
    condainfo: Optional[CondaInfo],
) -> None:
    """Validate new package name.

    It should raise :class:``quetz.errors.ValidationError`` if
    a package is not valid.

    :param str package_name:
        name of the package

    :param str channel_name:
        name of channel with the package

    :param BinaryIO file_handler:
       handler to the package file, it can be None if a package is created but
       no file was yet uploaded

    :param CondaInfo condainfo:
       CondaInfo instance with package metadata, it can be None if file was not
       uploaded
    """
