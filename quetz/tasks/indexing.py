# Copyright 2020 Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import json
import logging
import numbers
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

import quetz.config
from quetz import channel_data, repo_data
from quetz.condainfo import MAX_CONDA_TIMESTAMP
from quetz.db_models import PackageVersion
from quetz.utils import add_static_file, add_temp_static_file

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


def validate_packages(dao, pkgstore, channel_name):
    # for now we're just validating the size of the uploaded file
    logger.info("Starting package validation")

    if type(pkgstore).__name__ == "S3Store":
        fs_chan = pkgstore._bucket_map(channel_name)
    elif type(pkgstore).__name__ == "LocalStore":
        fs_chan = os.path.abspath(os.path.join(pkgstore.channels_dir, channel_name))

    logger.info(f"Checking {fs_chan}")
    ls_dirs = pkgstore.fs.ls(f"{fs_chan}", detail=True)
    dirs = [d['name'].rsplit('/', 1)[1] for d in ls_dirs if d['type'] == 'directory']

    for subdir in dirs:
        ls_result = pkgstore.fs.ls(f"{fs_chan}/{subdir}", detail=True)

        ls_result_set = set([(res["name"].rsplit('/', 1)[1]) for res in ls_result])
        db_result = [
            (res.filename, json.loads(res.info)["size"])
            for res in dao.db.query(PackageVersion).filter(
                PackageVersion.channel_name == channel_name,
                PackageVersion.platform == subdir,
            )
        ]
        db_result_set = set((res[0] for res in db_result))

        difference = ls_result_set ^ db_result_set

        logger.info(f"Differing files: {difference}")

        in_ls_not_db = ls_result_set - db_result_set
        in_db_not_ls = db_result_set - ls_result_set

        valid, inexistant, wrong_size = 0, 0, 0

        # remove all files that are in database and not uploaded
        for f in in_db_not_ls:
            logger.warning(f"Removing non-existent file from database {f}")
            db_pkg_to_delete = (
                dao.db.query(PackageVersion)
                .filter(
                    PackageVersion.channel_name == channel_name,
                    PackageVersion.platform == subdir,
                    PackageVersion.filename == f,
                )
                .one()
            )
            dao.db.delete(db_pkg_to_delete)
            inexistant += 1

        db_dict = dict(db_result)
        for f in ls_result:
            filename = f["name"].rsplit('/', 1)[1]
            if filename in db_dict:
                if db_dict[filename] != f["size"]:
                    # size of file in db and on filesystem does not match!
                    logger.error(
                        f"File size differs for {filename}: "
                        f"{f['size']} vs {db_dict[filename]}"
                    )
                    pkgstore.delete_file(
                        channel_name,
                        f"{subdir}/{filename}",
                    )
                    db_pkg_to_delete = (
                        dao.db.query(PackageVersion)
                        .filter(
                            PackageVersion.channel_name == channel_name,
                            PackageVersion.platform == subdir,
                            PackageVersion.filename == filename,
                        )
                        .one()
                    )
                    dao.db.delete(db_pkg_to_delete)
                    wrong_size += 1
                else:
                    valid += 1

        dao.db.commit()

        logger.info(f"\n\nSUBDIR: {subdir}")
        logger.info(f"On filesystem: {in_ls_not_db}")
        logger.info(f"In database, not uploaded: {in_db_not_ls}")

        logger.info(f"Valid files: {valid}")
        logger.info(f"Wrong size: {wrong_size}")
        logger.info(f"Not uploaded: {inexistant}")

    update_indexes(dao, pkgstore, channel_name)


def update_indexes(dao, pkgstore, channel_name, subdirs=None):
    jinjaenv = _jinjaenv()
    channeldata = channel_data.export(dao, channel_name)

    if subdirs is None:
        subdirs = sorted(channeldata["subdirs"], key=_subdir_key)

    # Generate channeldata.json and its compressed version
    chandata_json = json.dumps(channeldata, indent=2, sort_keys=False)
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

    tempdir = tempfile.TemporaryDirectory()
    tempdir_path = Path(tempdir.name)

    pm = quetz.config.get_plugin_manager()

    for sdir in subdirs:
        logger.debug(f"creating indexes for subdir {sdir} of channel {channel_name}")
        raw_repodata = repo_data.export(dao, channel_name, sdir)

        pm.hook.post_index_creation(
            raw_repodata=raw_repodata,
            channel_name=channel_name,
            subdir=sdir,
        )

        files[sdir] = []
        packages[sdir] = raw_repodata["packages"]

        repodata = json.dumps(raw_repodata, indent=2, sort_keys=False)

        add_temp_static_file(
            repodata, channel_name, sdir, "repodata.json", tempdir_path, files
        )

    pm.hook.post_package_indexing(
        tempdir=tempdir_path,
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
        add_static_file(subdir_index_html, channel_name, sdir, "index.html", pkgstore)

    # recursively walk through the tree
    tmp_suffix = uuid.uuid4().hex
    after_upload_move = []
    for path in tempdir_path.rglob('*.*'):
        rel_path = path.relative_to(tempdir_path)
        to_upload = open(path, 'rb')
        if len(rel_path.parts) == 2:
            channel_name, filename = rel_path.parts
            dest = f"{filename}{tmp_suffix}"
        elif len(rel_path.parts) == 3:
            channel_name, sdir, filename = rel_path.parts
            dest = f"{sdir}/{filename}{tmp_suffix}"
        else:
            raise NotImplementedError(
                "We can only handle channel_name/subdir/file.xyz OR"
                "channel_name/file.xyz"
            )

        logger.debug(f"Uploading {path} -> {channel_name} {dest}")
        if type(pkgstore).__name__ == "S3Store":
            with pkgstore._get_fs() as fs:
                bucket = pkgstore._bucket_map(channel_name)
                fs.put_file(path, f"{bucket}/{dest}")
        else:
            pkgstore.add_file(to_upload.read(), channel_name, dest)

        after_upload_move.append(dest)

    for f_to_move in after_upload_move:
        logger.debug(
            "Moving to final destination: "
            f"{f_to_move} -> {f_to_move[:-len(tmp_suffix)]}"
        )
        pkgstore.move_file(channel_name, f_to_move, f_to_move[: -len(tmp_suffix)])

    tempdir.cleanup()
