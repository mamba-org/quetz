import bz2
import json
import os
import uuid
from unittest import mock

import pytest

import quetz
from quetz import indexing
from quetz.db_models import Channel, Package, Profile, User


@pytest.fixture
def user(db):
    user = User(id=uuid.uuid4().bytes, username="bartosz")
    profile = Profile(name="Bartosz", avatar_url="http:///avatar", user=user)
    db.add(user)
    db.add(profile)
    db.commit()
    yield user


@pytest.fixture
def channel_name():
    return "my-channel"


@pytest.fixture
def package_name():
    return "mytestpackage"


@pytest.fixture
def package_format():
    return 'tarbz2'


@pytest.fixture
def package_file_name(package_name, package_format):
    if package_format == 'tarbz2':
        return f"{package_name}-0.1-0.tar.bz2"
    elif package_format == "conda":
        return f"{package_name}-0.1-0.conda"


@pytest.fixture
def channel(dao: "quetz.dao.Dao", channel_name, user):

    channel_data = Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, "owner")
    return channel


@pytest.fixture
def package_version(
    dao: "quetz.dao.Dao",
    user,
    channel,
    package_name,
    db,
    package_file_name,
    package_format,
):
    package_data = Package(name=package_name)

    dao.create_package(channel.name, package_data, user.id, "owner")
    package_info = (
        '{"run_exports": {"weak": ["otherpackage > 0.1"]}, "size": 100, "depends": []}'
    )
    version = dao.create_version(
        channel.name,
        package_name,
        package_format,
        "noarch",
        "0.1",
        "0",
        "0",
        package_file_name,
        package_info,
        user.id,
    )

    yield version


@pytest.fixture
def repodata_name(channel):
    package_name = f"{channel.name}-repodata-patches"
    return package_name


@pytest.fixture
def repodata_file_name(repodata_name):
    version = "0.1"
    build_str = "0"
    return f"{repodata_name}-{version}-{build_str}.tar.bz2"


@pytest.fixture
def revoke_instructions():
    return []


@pytest.fixture
def remove_instructions():
    return []


@pytest.fixture
def patched_package_name(package_file_name):
    # by default the name of the package in patch_instructions is the same
    # as the name of the dummy package
    # but we will change it in the test to test if we can patch .conda files
    # with .tar.bz2 instructions
    return package_file_name


@pytest.fixture
def patch_content(patched_package_name, revoke_instructions, remove_instructions):

    d = {}

    package_file_name = patched_package_name

    meta = {package_file_name: {"run_exports": {"weak": ["otherpackage > 0.2"]}}}

    if package_file_name.endswith(".tar.bz2"):
        d["packages"] = meta
    elif package_file_name.endswith(".conda"):
        d["packages.conda"] = meta

    d["revoke"] = revoke_instructions
    d["remove"] = remove_instructions

    return d


@pytest.fixture
def repodata_archive(repodata_file_name, patch_content):

    import tarfile
    import time
    from io import BytesIO

    tar_content = BytesIO()
    tar = tarfile.open(repodata_file_name, "w|bz2", fileobj=tar_content)

    patch_instructions = BytesIO(json.dumps(patch_content).encode('ascii'))

    info = tarfile.TarInfo(name='noarch')
    info.type = tarfile.DIRTYPE
    info.mode = 0o755
    info.mtime = time.time()
    tar.addfile(tarinfo=info)

    info = tarfile.TarInfo(name='noarch/patch_instructions.json')
    info.size = len(patch_instructions.getvalue())
    info.mtime = time.time()
    tar.addfile(tarinfo=info, fileobj=patch_instructions)
    tar.close()
    tar_content.seek(0)
    yield tar_content


@pytest.fixture
def package_repodata_patches(
    dao: "quetz.dao.Dao",
    user,
    channel,
    db,
    pkgstore,
    repodata_name,
    repodata_file_name,
    repodata_archive,
):

    package_name = repodata_name
    package_data = Package(name=package_name)

    dao.create_package(channel.name, package_data, user.id, "owner")
    package_info = '{"size": 100, "depends":[]}'
    package_format = "tarbz2"
    version = dao.create_version(
        channel.name,
        package_name,
        package_format,
        "noarch",
        "0.1",
        "0",
        "0",
        repodata_file_name,
        package_info,
        user.id,
    )

    pkgstore.add_package(repodata_archive, channel.name, f"noarch/{repodata_file_name}")

    return version


@pytest.fixture
def pkgstore(config):
    pkgstore = config.get_package_store()
    return pkgstore


@pytest.mark.parametrize("repodata_stem", ["repodata", "current_repodata"])
@pytest.mark.parametrize("compressed_repodata", [False, True])
@pytest.mark.parametrize(
    "revoke_instructions",
    [[], ["mytestpackage-0.1-0.tar.bz2"], ["nonexistentpackage-0.1-0.tar.bz2"]],
)
@pytest.mark.parametrize(
    "remove_instructions",
    [[], ["mytestpackage-0.1-0.tar.bz2"], ["nonexistentpackage-0.1-0.tar.bz2"]],
)
@pytest.mark.parametrize(
    "package_format,patched_package_name",
    [
        ("conda", "mytestpackage-0.1-0.tar.bz2"),
        ("conda", "mytestpackage-0.1-0.conda"),
        ("tarbz2", "mytestpackage-0.1-0.tar.bz2"),
        # this combination is no valid
        # (can't update tar.bz2 package with .conda instructions)
        # ("tarbz2","mytestpackage-0.1-0.conda"),
    ],
)
def test_post_package_indexing(
    pkgstore,
    dao,
    package_version,
    channel_name,
    package_repodata_patches,
    db,
    package_file_name,
    repodata_stem,
    compressed_repodata,
    revoke_instructions,
    remove_instructions,
    package_format,
    patched_package_name,
):
    def get_db():
        yield db

    with mock.patch("quetz_repodata_patching.main.get_db", get_db):
        indexing.update_indexes(dao, pkgstore, channel_name)

    ext = "json.bz2" if compressed_repodata else "json"
    open_ = bz2.open if compressed_repodata else open

    repodata_path = os.path.join(
        pkgstore.channels_dir, channel_name, "noarch", f"{repodata_stem}.{ext}"
    )

    assert os.path.isfile(repodata_path)

    with open_(repodata_path) as fid:
        data = json.load(fid)

    key = "packages" if package_format == 'tarbz2' else "packages.conda"

    packages = data[key]

    if package_file_name not in remove_instructions:
        assert packages[package_file_name]['run_exports'] == {
            "weak": ["otherpackage > 0.2"]
        }

    for revoked_pkg_name in revoke_instructions:
        try:
            revoked_pkg = packages[revoked_pkg_name]
        except KeyError:
            continue
        assert revoked_pkg.get("revoked", False)
        assert 'package_has_been_revoked' in revoked_pkg["depends"]

    for removed_pkg_name in remove_instructions:
        assert removed_pkg_name not in packages
        if removed_pkg_name == package_file_name:
            assert removed_pkg_name in data.get("removed", ())

    orig_repodata_path = os.path.join(
        pkgstore.channels_dir,
        channel_name,
        "noarch",
        f"{repodata_stem}_from_packages.{ext}",
    )

    assert os.path.isfile(orig_repodata_path)
    with open_(orig_repodata_path) as fid:
        data = json.load(fid)
    package_data = data[key][package_file_name]
    assert package_data['run_exports'] == {"weak": ["otherpackage > 0.1"]}
    assert not package_data.get("revoked", False)
    assert "package_has_been_revoked" not in package_data
    assert not data.get("removed")
