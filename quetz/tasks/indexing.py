# Copyright 2020 Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import json
import logging
import numbers
from datetime import datetime, timezone

from jinja2 import Environment, PackageLoader, select_autoescape

import quetz.config
from quetz import channel_data, repo_data
from quetz.condainfo import MAX_CONDA_TIMESTAMP
from quetz.utils import add_static_file

_iec_prefixes = (
    # IEEE 1541 - IEEE Standard for Prefixes for Binary Multiples
    # ISO/IEC 80000-13:2008 Clause 4 binary prefixes
    # https://en.wikipedia.org/wiki/Binary_prefix
    (1024 * 1024 * 1024 * 1024, "{:.2f} TiB"),
    (1024 * 1024 * 1024, "{:.2f} GiB"),
    (1024 * 1024, "{:.1f} MiB"),
    (1024, "{:.0f} KiB"),
    (1, "{:.0f} B"),
)

logger = logging.getLogger("quetz")


def _iec_bytes(n):
    # Return human-readable string representing n in bytes in IEC format
    for e, f in _iec_prefixes:
        if n >= e:
            return f.format(n / e)
    return f"{n} B"


def _strftime(date, date_format):
    if isinstance(date, numbers.Real):
        if date > MAX_CONDA_TIMESTAMP:
            date //= 1000
        date = datetime.fromtimestamp(date, timezone.utc)

    if isinstance(date, datetime):
        return date.strftime(date_format)


def _opt_href(text, link):
    if link:
        return f"<a href={link}>{text}</a>"
    else:
        return text


def _jinjaenv():
    env = Environment(
        loader=PackageLoader("quetz", "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.trim_blocks = True
    env.lstrip_blocks = True
    env.filters["iec_bytes"] = _iec_bytes
    env.filters["strftime"] = _strftime
    env.filters["opt_href"] = _opt_href
    return env


_subdir_order = {
    # This determines the ordering of subdirectories in index.html
    "linux-64": "!000",
    "osx-64": "!001",
    "win-64": "!002",
    # New architectures go here
    "noarch": "~~~~~~~",  # sorts last
}


def _subdir_key(dir):
    return _subdir_order.get(dir, dir)


def update_indexes(dao, pkgstore, channel_name, subdirs=None):
    jinjaenv = _jinjaenv()
    channeldata = channel_data.export(dao, channel_name)

    if subdirs is None:
        subdirs = sorted(channeldata["subdirs"], key=_subdir_key)

    # Generate channeldata.json and its compressed version
    chandata_json = json.dumps(channeldata, indent=2, sort_keys=True)
    add_static_file(chandata_json, channel_name, None, "channeldata.json", pkgstore)

    # Generate index.html for the "root" directory
    channel_index = jinjaenv.get_template("channeldata-index.html.j2").render(
        title=channel_name,
        packages=channeldata["packages"],
        subdirs=subdirs,
        current_time=datetime.now(timezone.utc),
    )

    add_static_file(channel_index, channel_name, None, "index.html", pkgstore)

    # NB. No rss.xml is being generated here
    files = {}
    packages = {}
    subdir_template = jinjaenv.get_template("subdir-index.html.j2")
    for sdir in subdirs:
        logger.debug(f"creating indexes for subdir {sdir} of channel {channel_name}")
        raw_repodata = repo_data.export(dao, channel_name, sdir)

        files[sdir] = []
        packages[sdir] = raw_repodata["packages"]
        repodata = json.dumps(raw_repodata, indent=2, sort_keys=True)
        add_static_file(repodata, channel_name, sdir, "repodata.json", pkgstore, files)

    pm = quetz.config.get_plugin_manager()

    pm.hook.post_package_indexing(
        pkgstore=pkgstore,
        channel_name=channel_name,
        subdirs=subdirs,
        files=files,
        packages=packages,
    )

    for sdir in subdirs:
        # Generate subdir index.html
        subdir_index_html = subdir_template.render(
            title=f"{channel_name}/{sdir}",
            packages=packages[sdir],
            current_time=datetime.now(timezone.utc),
            add_files=files[sdir],
        )
        add_static_file(
            subdir_index_html, channel_name, sdir, f"{sdir}/index.html", pkgstore
        )
