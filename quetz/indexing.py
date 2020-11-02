# Copyright 2020 Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import bz2
import hashlib
import json
import numbers
from datetime import datetime, timezone

from jinja2 import Environment, PackageLoader, select_autoescape

from quetz import channel_data, repo_data
from quetz.condainfo import MAX_CONDA_TIMESTAMP
from quetz.config import get_plugin_manager

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


def update_indexes(dao, pkgstore, channel_name):
    jinjaenv = _jinjaenv()
    channeldata = channel_data.export(dao, channel_name)
    subdirs = sorted(channeldata["subdirs"], key=_subdir_key)

    # Generate channeldata.json and its compressed version
    chandata_json = json.dumps(channeldata, indent=2, sort_keys=True)
    pkgstore.add_file(
        bz2.compress(chandata_json.encode("utf-8")),
        channel_name,
        "channeldata.json.bz2",
    )
    pkgstore.add_file(chandata_json, channel_name, "channeldata.json")

    # Generate index.html for the "root" directory
    channel_template = jinjaenv.get_template("channeldata-index.html.j2")
    pkgstore.add_file(
        channel_template.render(
            title=channel_name,
            packages=channeldata["packages"],
            subdirs=subdirs,
            current_time=datetime.now(timezone.utc),
        ),
        channel_name,
        "index.html",
    )

    # NB. No rss.xml is being generated here

    subdir_template = jinjaenv.get_template("subdir-index.html.j2")
    for dir in subdirs:
        raw_repodata = repo_data.export(dao, channel_name, dir)

        repodata = json.dumps(raw_repodata, indent=2, sort_keys=True)
        md5_repodata = hashlib.md5()
        md5_repodata.update(repodata.encode("utf-8"))
        sha_repodata = hashlib.sha256()
        sha_repodata.update(repodata.encode("utf-8"))

        compressed_repodata = bz2.compress(repodata.encode("utf-8"))
        md5_compressed = hashlib.md5()
        md5_compressed.update(compressed_repodata)
        sha_compressed = hashlib.sha256()
        sha_compressed.update(compressed_repodata)

        add_files = []
        for fname in ("repodata.json", "current_repodata.json"):
            pkgstore.add_file(compressed_repodata, channel_name, f"{dir}/{fname}.bz2")
            pkgstore.add_file(repodata, channel_name, f"{dir}/{fname}")
            add_files.append(
                {
                    "name": f"{fname}",
                    "size": len(repodata),
                    "timestamp": datetime.now(timezone.utc),
                    "md5": md5_repodata.hexdigest(),
                    "sha256": sha_repodata.hexdigest(),
                }
            )
            add_files.append(
                {
                    "name": f"{fname}.bz2",
                    "size": len(compressed_repodata),
                    "timestamp": datetime.now(timezone.utc),
                    "md5": md5_compressed.hexdigest(),
                    "sha256": sha_compressed.hexdigest(),
                }
            )

        # Generate subdir index.html
        pkgstore.add_file(
            subdir_template.render(
                title=f"{channel_name}/{dir}",
                packages=raw_repodata["packages"],
                current_time=datetime.now(timezone.utc),
                add_files=add_files,
            ),
            channel_name,
            f"{dir}/index.html",
        )

    pm = get_plugin_manager()

    pm.hook.post_package_indexing()
