from typing import List

import fastapi
import pluggy

import quetz

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


@hookspec
def post_package_indexing(
    pkgstore: "quetz.pkgstores.PackageStore",
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
