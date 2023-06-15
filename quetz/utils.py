# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import bz2
import distutils
import gzip
import hashlib
import inspect
import logging
import secrets
import shlex
import string
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

from conda.models.match_spec import MatchSpec
from sqlalchemy import String, and_, cast, collate, not_, or_

from .db_models import Channel, Package, PackageVersion, User


def _parse_package_spec(package_name: str, package_metadata) -> tuple[str, str, str]:
    """Given a package name and metadata, return the package spec.

    Args:
        package_name (str): The package name in file format,
            e.g. "numpy-1.23.4-py39hefdcf20_0.tar.bz2"
        package_metadata (_type_): Metadata of the package,
            e.g. from repodata.json

    Returns:
        tuple[str, str, str]: (name, version, build-string)
    """

    # spec = _parse_spec_str(package_spec)
    # return spec.get("name", ""), spec.get("version", ""), spec.get("build", "")
    # TODO: the package spec here looks like "numpy-1.23.4-py39hefdcf20_0.tar.bz2"
    # and does not have "="
    spec = package_name.split("-")
    return spec[0], spec[1] if len(spec) > 1 else "", spec[2] if len(spec) > 2 else ""


def _check_package_match(
    package_spec: tuple[str, str, str],
    include_or_exclude_list: list[str],
) -> bool:
    """
    Check if the given package specification matches
    with the given include or exclude list.
    Returns true if a match is found.
    """
    name, version, build = package_spec
    for pattern in include_or_exclude_list:
        # TODO: validate if this matches with our current implementation
        if MatchSpec(pattern).match(
            {"name": name, "version": version, "build": build, "build_number": 0}
        ):
            return True

    return False


def check_package_membership(
    channel: Channel,
    package_name: str,
    package_metadata: dict,
    remote_host: str,
):
    """
    Check if a package should be in a channel according
    to the rules defined in the channel metadata.

    Args:
        channel (Channel): Channel object returned from the database
        package_name (str): name of the package in file format,
            e.g. "numpy-1.23.4-py39hefdcf20_0.tar.bz2"
        package_metadata (dict): package metadata,
            information that can be found in repodata.json for example
        includelist (Union[list[str], dict, None], optional):
        excludelist (Union[list[str], dict, None], optional):

    Returns:
        bool: if the package should be in this channel or not according to the rules.
    """
    package_spec = _parse_package_spec(package_name, package_metadata)
    metadata = channel.load_channel_metadata()
    if (includelist := metadata['includelist']) is not None:
        # Example: { "main": ["numpy", "pandas"], "r": ["r-base"]}
        if isinstance(includelist, dict):
            if channel.name not in includelist:
                include_package = False
            channel_includelist = includelist[remote_host.split("/")[-1]]
            include_package = _check_package_match(package_spec, channel_includelist)
        # Example: ["numpy", "pandas", "r-base"]
        elif isinstance(includelist, list):
            include_package = _check_package_match(package_spec, includelist)

    # TODO: implement excludelist

    return include_package


def add_static_file(contents, channel_name, subdir, fname, pkgstore, file_index=None):
    if type(contents) is not bytes:
        raw_file = contents.encode("utf-8")
    else:
        raw_file = contents
    bz2_file = bz2.compress(raw_file)
    gzp_file = gzip.compress(raw_file)

    path = f"{subdir}/{fname}" if subdir else fname
    pkgstore.add_file(bz2_file, channel_name, f"{path}.bz2")
    pkgstore.add_file(gzp_file, channel_name, f"{path}.gz")
    pkgstore.add_file(raw_file, channel_name, f"{path}")

    if file_index:
        add_entry_for_index(file_index, subdir, fname, raw_file)
        add_entry_for_index(file_index, subdir, f"{fname}.bz2", bz2_file)
        add_entry_for_index(file_index, subdir, f"{fname}.gz", gzp_file)


def add_temp_static_file(
    contents, channel_name, subdir, fname, temp_dir, file_index=None
):
    if type(contents) is not bytes:
        raw_file = contents.encode("utf-8")
    else:
        raw_file = contents

    temp_dir = Path(temp_dir)

    if subdir:
        path = temp_dir / channel_name / subdir
    else:
        path = temp_dir / channel_name

    if not path.exists():
        path.mkdir(exist_ok=True, parents=True)

    file_path = path / fname

    with open(file_path, 'wb') as fo:
        fo.write(raw_file)

    bz2_file = bz2.compress(raw_file)
    gzp_file = gzip.compress(raw_file)

    with open(f"{file_path}.bz2", 'wb') as fo:
        fo.write(bz2_file)

    with open(f"{file_path}.gz", 'wb') as fo:
        fo.write(gzp_file)

    if file_index:
        add_entry_for_index(file_index, subdir, fname, raw_file)
        add_entry_for_index(file_index, subdir, f"{fname}.bz2", bz2_file)
        add_entry_for_index(file_index, subdir, f"{fname}.gz", gzp_file)


def add_entry_for_index(files, subdir, fname, data_bytes):
    md5 = hashlib.md5()
    sha = hashlib.sha256()

    md5.update(data_bytes)
    sha.update(data_bytes)

    if subdir:
        files[subdir].append(
            {
                "name": fname,
                "size": len(data_bytes),
                "timestamp": datetime.now(timezone.utc),
                "md5": md5.hexdigest(),
                "sha256": sha.hexdigest(),
            }
        )


def parse_query(search_type, query):
    accepted_filters = []
    if search_type == 'package':
        accepted_filters = [
            'channel',
            'description',
            'summary',
            # 'format',
            'platform',
            # 'version',
            # 'uploader',
        ]
    elif search_type == 'channel':
        accepted_filters = ['description', 'private']
    query = unquote(query.strip())

    args = shlex.split(query)
    keywords = []
    filters = []

    for arg in args:
        if ':' in arg:
            key, val = arg.split(':', 1)
            if (
                key.startswith('-') and key[1:] in accepted_filters
            ) or key in accepted_filters:
                filters.append((key, val.split(',')))
        else:
            arg = arg.strip('"').strip("'")
            keywords.append(arg)

    return keywords, filters


def apply_custom_query(search_type, db, keywords, filters):
    keyword_conditions = []
    negation_argument = None
    each_keyword_condition = None
    for i, each_keyword in enumerate(keywords):
        if each_keyword == 'NOT':
            negation_argument = keywords[i + 1]
            if search_type == 'package':
                each_keyword_condition = Package.name.notlike(f'%{negation_argument}%')
            elif search_type == 'channel':
                each_keyword_condition = collate(Channel.name, "und-x-icu").notlike(
                    f'%{negation_argument}%'
                )
            else:
                raise KeyError(search_type)
        else:
            if each_keyword != negation_argument:
                if search_type == 'package':
                    each_keyword_condition = Package.name.ilike(f'%{each_keyword}%')
                elif search_type == 'channel':
                    each_keyword_condition = collate(Channel.name, "und-x-icu").ilike(
                        f'%{each_keyword}%'
                    )
                else:
                    raise KeyError(search_type)
        keyword_conditions.append(each_keyword_condition)

    query = db.filter(and_(True, *keyword_conditions))

    for each_filter in filters:
        key, values = each_filter
        negate = False
        if key.startswith('-'):
            key = key[1:]
            negate = True
        each_filter_conditions = []
        for each_val in values:
            each_val_condition = None
            each_val = each_val.strip('"').strip("'")
            if search_type == 'package':
                if key == 'channel':
                    each_val_condition = collate(Channel.name, "und-x-icu").ilike(
                        f'%{(each_val)}%'
                    )
                elif key == 'description':
                    each_val_condition = Package.description.contains(each_val)
                elif key == 'summary':
                    each_val_condition = Package.summary.contains(each_val)
                elif key == 'format':
                    each_val_condition = cast(
                        PackageVersion.package_format, String
                    ).ilike(f'%{(each_val)}%')
                elif key == 'platform':
                    each_val_condition = Package.platforms.ilike(f'%{(each_val)}%')
                elif key == 'version':
                    each_val_condition = PackageVersion.version.ilike(f'%{(each_val)}%')
                elif key == 'uploader':
                    each_val_condition = User.username.ilike(f'%{(each_val)}%')
                else:
                    raise KeyError(key)
            elif search_type == 'channel':
                if key == 'description':
                    each_val_condition = Channel.description.contains(each_val)
                elif key == 'private':
                    each_val_condition = Channel.private.is_(
                        bool(distutils.util.strtobool(each_val))
                    )
                else:
                    raise KeyError(key)
            else:
                raise KeyError(search_type)
            each_filter_conditions.append(each_val_condition)
        if negate:
            query = query.filter(not_(or_(*each_filter_conditions)))
        else:
            query = query.filter(or_(*each_filter_conditions))
    return query


class TicToc:
    def __init__(self, description):
        self.description = description

    def __enter__(self):
        self.start = time.time()

    def __exit__(self, ty, val, tb):
        self.stop = time.time()
        print(f"[TOC] {self.description}: {self.stop - self.start}")

    @property
    def elapsed(self):
        return self.stop - self.start


def generate_random_key(length=32):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))


def background_task_wrapper(func: Callable, logger: logging.Logger) -> Callable:
    task_name = func.__name__

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> None:
        task_id = uuid.uuid4()

        try:
            func(*args, **kwargs)
            logger.info(f"[{task_id}] Finished {task_name} successfully")
        except Exception as e:
            logger.error(f"[{task_id}] Failed Permanently {task_name} with error: {e}")

            func_args = inspect.signature(func).bind(*args, **kwargs).arguments

            func_args_str = ", ".join(
                f"{name}={repr(value)}" for name, value in func_args.items()
            )

            logger.error(
                f"[{task_id}] Started {task_name} with arguments: {func_args_str}"
            )

            exc_type, exc_value, exc_traceback = sys.exc_info()

            traceback.print_exception(
                exc_type, exc_value, exc_traceback, limit=25, file=sys.stdout
            )

    return wrapper
