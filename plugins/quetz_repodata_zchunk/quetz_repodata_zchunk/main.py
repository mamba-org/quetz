import bz2
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone

import quetz
from quetz.tasks.indexing import _jinjaenv


def update_index(pkgstore, updated_files, channel_name, subdir, packages):
    "update index.html in platform subdir"

    add_files = []

    for fname, data in updated_files:
        md5 = hashlib.md5()
        sha = hashlib.sha256()
        if not isinstance(data, bytes):
            data_bytes = data.encode("utf-8")
        else:
            data_bytes = data
        md5.update(data_bytes)
        sha.update(data_bytes)

        add_files.append(
            {
                "name": f"{fname}",
                "size": len(data_bytes),
                "timestamp": datetime.now(timezone.utc),
                "md5": md5.hexdigest(),
                "sha256": sha.hexdigest(),
            }
        )

    jinjaenv = _jinjaenv()
    subdir_template = jinjaenv.get_template("subdir-index.html.j2")

    pkgstore.add_file(
        subdir_template.render(
            title=f"{channel_name}/{subdir}",
            packages=packages,
            current_time=datetime.now(timezone.utc),
            add_files=add_files,
        ),
        channel_name,
        f"{subdir}/index.html",
    )


@quetz.hookimpl
def post_package_indexing(
    pkgstore: "quetz.pkgstores.PackageStore", channel_name, subdirs
):
    for subdir in subdirs:
        updated_files = []
        for fname in ["repodata"]:
            fs = pkgstore.serve_path(channel_name, f"{subdir}/{fname}.json")

            repodata_str = fs.read()
            repodata = json.loads(repodata_str)

            _, path1 = tempfile.mkstemp()
            _, path2 = tempfile.mkstemp()

            with open(path1, 'wb') as f:
                f.write(repodata_str)

            try:
                subprocess.check_call(['zck', path1, '-o', path2])
            except FileNotFoundError:
                raise RuntimeError(
                    'zchunk does not seem to be installed, '
                    'you can install it with:\n'
                    'mamba install zchunk -c conda-forge'
                )
            except subprocess.CalledProcessError:
                raise RuntimeError('Error calling zck on repodata.')
            finally:
                os.remove(path1)

            with open(path2, 'rb') as f:
                repodata_zck = f.read()

            os.remove(path2)

            pkgstore.add_file(repodata_zck, channel_name, f'{subdir}/{fname}.json.zck')
            updated_files.append((f'{fname}.json.zck', repodata_zck))

            pkgstore.add_file(repodata_str, channel_name, f'{subdir}/{fname}.json')
            updated_files.append((f'{fname}.json', repodata_str))

            repodata_bz2 = bz2.compress(repodata_str)
            pkgstore.add_file(repodata_bz2, channel_name, f'{subdir}/{fname}.json.bz2')
            updated_files.append((f'{fname}.json.bz2', repodata_bz2))

            packages = repodata["packages"]
            packages.update(repodata["packages.conda"])

        update_index(pkgstore, updated_files, channel_name, subdir, packages)
