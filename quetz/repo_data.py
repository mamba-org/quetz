# Copyright 2020 Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import json

from quetz import db_models


def export(dao, channel_name, subdir):

    if dao.is_active_platform(channel_name, subdir):
        repodata = {
            "info": {"subdir": subdir},
            "packages": {},
            "packages.conda": {},
            "repodata_version": 1,
        }
        packages = repodata["packages"]
        packages_conda = repodata["packages.conda"]

        for filename, info, format, time_created in dao.get_package_infos(
            channel_name, subdir
        ):
            data = json.loads(info)
            data['date_modified'] = time_created.isoformat()
            if format == db_models.PackageFormatEnum.conda:
                packages_conda[filename] = data
            else:
                packages[filename] = data

        return repodata
    else:
        return None
