from pathlib import Path
from typing import BinaryIO, List, Optional

import fastapi
import pluggy

import quetz
from quetz.condainfo import CondaInfo

hookspec = pluggy.HookspecMarker("quetz")


@hookspec
def register_router() -> 'fastapi.APIRouter':
    """add extra endpoints to the url tree.

    It should return an :py:class:`fastapi.APIRouter` with new endpoints definitions.
    By default it will be added to the root of the urlscheme"""


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
    pass


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
def post_index_creation(
    raw_repodata: dict,
    channel_name: str,
    subdir: str,
) -> None:
    """hook for post-processsing after creating package index.

    :param dict raw_repodata:
        the package index

    :param str channel_name:
        the channel name

    :param str subdir:
        the subdirectory to which belongs the package index
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


@hookspec
def check_additional_permissions(db, user_id, user_role) -> bool:
    """
    Check if the user has appropriate permissions

    :param str user_id:
        id of the user
    """
    return True
