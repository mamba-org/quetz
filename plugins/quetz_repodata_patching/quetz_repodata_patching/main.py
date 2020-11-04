import bz2
import json
import tarfile
from contextlib import contextmanager
from io import BytesIO
from zipfile import ZipFile

import zstandard

import quetz
from quetz.db_models import PackageFormatEnum, PackageVersion
from quetz.deps import get_db


def update_dict(packages, instructions):
    for pkg, info in instructions.items():
        if pkg in packages:
            packages[pkg].update(info)


def patch_repodata(repodata, patches):
    for key in ("packages", "packages.conda"):
        packages = repodata.get(key, {})
        remove_set = set(patches.get("remove", ()))
        revoke_set = set(patches.get("revoke", ()))

        # patch packages
        update_dict(packages, patches.get(key, {}))

        if key == "packages.conda":
            # in the conda-build implementation
            # the conda packages can be also patched
            # with the .tar.bz2 instructions

            instructions = patches.get("packages", {})
            new_patches = {
                k.replace(".tar.bz2", ".conda"): v for k, v in instructions.items()
            }
            update_dict(packages, new_patches)

            remove_set = remove_set.union(
                {s.replace(".tar.bz2", ".conda") for s in remove_set}
            )
            revoke_set = revoke_set.union(
                {s.replace(".tar.bz2", ".conda") for s in revoke_set}
            )

        # revoke packages
        for revoked_pkg_name in revoke_set:
            if revoked_pkg_name not in packages:
                continue
            package = packages[revoked_pkg_name]
            package['revoked'] = True
            package["depends"].append('package_has_been_revoked')

        # remove packages
        repodata.setdefault("removed", [])
        for removed_pkg_name in remove_set:
            popped = packages.pop(removed_pkg_name, None)
            if popped:
                repodata["removed"].append(removed_pkg_name)


@contextmanager
def extract_from_tarfile(fs):
    """extract patch_instruction.json from tar.bz2 package"""
    with tarfile.open(mode='r:bz2', fileobj=fs) as patch_archive:
        yield patch_archive


@contextmanager
def extract_from_conda(fs):
    """extract patch_instruction.json from .conda package"""
    with ZipFile(fs) as zf:
        pkgtars = [_ for _ in zf.namelist() if _.startswith("pkg-")]
        pkgtar = pkgtars[0]
        with zf.open(pkgtar) as zfobj:
            if pkgtar.endswith(".zst"):
                zstd = zstandard.ZstdDecompressor()
                fobj = BytesIO(zstd.stream_reader(zfobj).read())
            else:
                fobj = zfobj
            with tarfile.open(fileobj=fobj, mode="r") as tar:
                yield tar


def _load_instructions(tar, path):
    patch_instructions = json.load(tar.extractfile(path))
    return patch_instructions


@quetz.hookimpl
def post_package_indexing(
    pkgstore: "quetz.pkgstores.PackageStore", channel_name, subdirs
):

    get_db_manager = contextmanager(get_db)
    with get_db_manager() as db:

        query = (
            db.query(PackageVersion)
            .filter(
                PackageVersion.channel_name == channel_name,
                PackageVersion.package_name == f"{channel_name}-repodata-patches",
            )
            .order_by(PackageVersion.version.desc())
        )
        patches_pkg = query.one_or_none()

    if patches_pkg:
        filename = patches_pkg.filename
        fs = pkgstore.serve_path(channel_name, "noarch/" + filename)
        package_format = patches_pkg.package_format

        if package_format == PackageFormatEnum.tarbz2:
            extract_ = extract_from_tarfile
        else:
            extract_ = extract_from_conda

        with extract_(fs) as tar:

            for subdir in subdirs:
                path = f"{subdir}/patch_instructions.json"

                patch_instructions = _load_instructions(tar, path)

                for fname in ("repodata", "current_repodata"):
                    fs = pkgstore.serve_path(channel_name, f"{subdir}/{fname}.json")

                    repodata_str = fs.read()
                    repodata = json.loads(repodata_str)

                    pkgstore.add_file(
                        repodata_str,
                        channel_name,
                        f"{subdir}/{fname}_from_packages.json",
                    )
                    compressed_repodata_str = bz2.compress(repodata_str)

                    pkgstore.add_file(
                        compressed_repodata_str,
                        channel_name,
                        f"{subdir}/{fname}_from_packages.json.bz2",
                    )

                    patch_repodata(repodata, patch_instructions)

                    patched_repodata_str = json.dumps(repodata)
                    compressed_patched_repodata_str = bz2.compress(
                        patched_repodata_str.encode('utf-8')
                    )

                    pkgstore.add_file(
                        patched_repodata_str, channel_name, f"{subdir}/{fname}.json"
                    )
                    pkgstore.add_file(
                        compressed_patched_repodata_str,
                        channel_name,
                        f"{subdir}/{fname}.json.bz2",
                    )
