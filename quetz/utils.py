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
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

from conda.models.dist import Dist
from conda.models.match_spec import MatchSpec
from sqlalchemy import String, and_, cast, collate, not_, or_

from .db_models import Channel, Package, PackageVersion, User


def parse_package_filename(package_name: str) -> tuple[str, str, str]:
    """Given a package name and metadata, return the package spec.

    Args:
        package_name (str): The package name in file format,
            e.g. "numpy-1.23.4-py39hefdcf20_0.tar.bz2"

    Returns:
        tuple[str, str, str]: (name, version, build-string)
    """
    dist_obj = Dist.from_string(package_name)

    return dist_obj.name, dist_obj.version, dist_obj.build_string


def check_package_match(
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
        if MatchSpec(pattern).match(
            {"name": name, "version": version, "build": build, "build_number": 0}
        ):
            return True

    return False


class MembershipAction(Enum):
    INCLUDE = "include"  # package should be added to the channel
    IGNORE = "ignore"  # package is not member of this channel but of another
    REMOVE = "remove"  # package is not member of any channel


def get_matching_hosts(
    include_or_exclude_list: dict, package_spec: tuple[str, str, str]
) -> list[str]:
    """
    Return the names of all matching hosts from the includelist
    that whould allow _this_ package spec.
    include_or_exclude_list:
        e.g. { "remote1": ["numpy", "pandas"], "remote2": ["r-base"]}
    """
    name, version, build = package_spec
    matching_hosts = []
    for host, patterns in include_or_exclude_list.items():
        if check_package_match(package_spec, patterns):
            matching_hosts.append(host)
    return matching_hosts


def check_package_membership(
    channel: Channel,
    channel_metadata: dict,
    package_name: str,
    package_metadata: dict,
    remote_host: str,
) -> MembershipAction:
    """
    Check if a package should be in a channel according
    to the rules defined in the channel metadata.

    The function returns a representation of the treatment the package
    should receive (include / exclude / ignore).

    A package should be:
    * included if is in the includelist (for this channel)
    * excluded if is in the excludelist (for this channel)
        this means that existing versions of the package will be removed
    * ignored if it does not match the includelist for this channel
        this does not remove the package since it might
        match the includelist of another channel

    Args:
        channel (Channel): mirror Channel object returned from the database
        package_name (str): name of the package in file format,
            e.g. "numpy-1.23.4-py39hefdcf20_0.tar.bz2"
        package_metadata (dict): package metadata,
            information that can be found in repodata.json for example
        includelist (Union[list[str], dict, None], optional):
            list of packages or dict of {channel: [packages]} that should be included
        excludelist (Union[list[str], dict, None], optional):
            list of packages or dict of {channel: [packages]} that should be excluded

    Returns:
        MembershipAction: this determines if the package should be included,
            ignored or removed from the channel
    """
    package_spec = parse_package_filename(package_name)

    incl_act = MembershipAction.INCLUDE
    exclude_now = False
    if (includelist := channel_metadata['includelist']) is not None:
        # Example: { "main": ["numpy", "pandas"], "r": ["r-base"]}
        if isinstance(includelist, dict):
            matches = get_matching_hosts(includelist, package_spec)
            if remote_host in matches or remote_host.split("/")[-1] in matches:
                incl_act = MembershipAction.INCLUDE
            elif len(matches) > 0:  # we have a match but not for this host
                incl_act = MembershipAction.IGNORE
            else:
                incl_act = MembershipAction.REMOVE

        # Example: ["numpy", "pandas", "r-base"]
        elif isinstance(includelist, list):
            if check_package_match(package_spec, includelist):
                incl_act = MembershipAction.INCLUDE
            else:
                incl_act = MembershipAction.REMOVE

    # for exclude list, we only check the current host
    if (excludelist := channel_metadata['excludelist']) is not None:
        exclude_now = False
        if isinstance(excludelist, dict):
            if channel.name in excludelist:
                channel_excludelist = excludelist[remote_host.split("/")[-1]]
                exclude_now = check_package_match(package_spec, channel_excludelist)
            else:
                exclude_now = False
        elif isinstance(excludelist, list):
            exclude_now = check_package_match(package_spec, excludelist)

    # package not explicitly excluded? -> listen to include action
    if not exclude_now:
        return incl_act
    else:
        return MembershipAction.REMOVE


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
