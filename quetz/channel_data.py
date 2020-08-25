# Copyright 2020 Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import json
from conda.exports import VersionOrder

CHANNELDATA_OPTIONAL_FIELDS = (
    "description",
    "dev_url",
    "doc_source_url",
    "doc_url",
    "home",
    "icon_hash",
    "icon_url",
    "license",
    "license_family",
    "spdx_license",
    "source_git_url",
    "reference_package",
    "source_url",
    "summary",
    "version",
)
CHANNELDATA_BINARY_FIELDS = (
    "activate.d",
    "deactivate.d",
    "post_link",
    "pre_link",
    "pre_unlink",
    "binary_prefix",
    "text_prefix",
)


def combine(old_data, new_data):
    if old_data is None:
        data = new_data
    else:
        data = {}
        newer = VersionOrder(old_data.get("version", "0")) < VersionOrder(
            new_data.get("version", "0")
        )
        for field in CHANNELDATA_BINARY_FIELDS:
            data[field] = any(
                (new_data.get(field, False), old_data.get(field, False))
            )

        for field in ("keywords", "identifiers", "tags"):
            if newer and new_data.get(field):
                data[field] = new_data[field]
            else:
                data[field] = old_data.get(field, {})

        for field in CHANNELDATA_OPTIONAL_FIELDS:
            if newer and field in new_data:
                data[field] = new_data[field]
            elif field in old_data:
                data[field] = old_data[field]

        run_exports = old_data.get("run_exports", {})
        if "run_exports" in new_data:
            if new_data["run_exports"]:
                run_exports[new_data["version"]] = new_data["run_exports"]
        data["run_exports"] = run_exports

        data["timestamp"] = max(
            old_data.get("timestamp", 0), new_data.get("timestamp", 0)
        )

        data["subdirs"] = sorted(
            list(
                set(new_data.get("subdirs", []))
                | set(old_data.get("subdirs", []))
            )
        )

    data = dict(sorted(data.items(), key=lambda item: item[0]))

    return data


def export(dao, channel_name):
    channeldata = {"channeldata_version": 1, "packages": {}, "subdirs": {}}
    packages = channeldata["packages"]
    subdirs = set()

    for name, info in dao.get_channel_datas(channel_name):
        if info is not None:
            data = json.loads(info)
            packages[name] = data
            subdirs = set(data["subdirs"]) | subdirs

    channeldata["subdirs"] = list(subdirs)

    return channeldata
