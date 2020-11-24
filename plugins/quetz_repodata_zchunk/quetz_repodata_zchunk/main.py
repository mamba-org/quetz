import bz2
import json
import os
import subprocess
import tempfile

import quetz
from quetz.utils import add_entry_for_index


@quetz.hookimpl
def post_package_indexing(
    pkgstore: "quetz.pkgstores.PackageStore", channel_name, subdirs, files, packages
):
    for subdir in subdirs:
        fname = "repodata"
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
        add_entry_for_index(files, subdir, f'{fname}.json.zck', repodata_zck)

        pkgstore.add_file(repodata_str, channel_name, f'{subdir}/{fname}.json')
        add_entry_for_index(files, subdir, f'{fname}.json', repodata_str)

        repodata_bz2 = bz2.compress(repodata_str)
        pkgstore.add_file(repodata_bz2, channel_name, f'{subdir}/{fname}.json.bz2')
        add_entry_for_index(files, subdir, f'{fname}.json.bz2', repodata_bz2)

        packages[subdir] = repodata["packages"]
        packages[subdir].update(repodata["packages.conda"])
