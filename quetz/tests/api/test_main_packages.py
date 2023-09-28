import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import BinaryIO, Callable, Tuple, Union

import pytest

from quetz import hookimpl
from quetz.authorization import MAINTAINER, MEMBER, OWNER, SERVER_OWNER
from quetz.condainfo import CondaInfo
from quetz.config import Config
from quetz.dao import Dao
from quetz.db_models import ChannelMember, Package, PackageMember, PackageVersion
from quetz.errors import ValidationError
from quetz.rest_models import BaseApiKey, Channel
from quetz.tasks.indexing import update_indexes


@pytest.mark.parametrize("package_role", [OWNER, MAINTAINER, MEMBER])
@pytest.mark.parametrize("channel_role", [MEMBER])
def test_delete_package(
    auth_client, public_package, public_channel, dao, db, package_role, user
):
    response = auth_client.delete(
        f"/api/channels/{public_channel.name}/packages/{public_package.name}"
    )

    if package_role == MEMBER:
        assert response.status_code == 403
        return

    package = (
        db.query(Package).filter(Package.name == public_package.name).one_or_none()
    )

    if package_role == MEMBER:
        assert response.status_code == 403
        assert package is not None
    else:
        assert response.status_code == 200
        assert package is None


def test_delete_package_non_member(
    client, public_package, public_channel, dao, db, other_user
):
    response = client.get(f"/api/dummylogin/{other_user.username}")

    assert response.status_code == 200

    response = client.delete(
        f"/api/channels/{public_channel.name}/packages/{public_package.name}"
    )

    assert response.status_code == 403

    package = (
        db.query(Package).filter(Package.name == public_package.name).one_or_none()
    )

    assert package is not None


def test_delete_package_versions_with_package(
    auth_client, public_channel, public_package, package_version, dao, db, pkgstore
):
    assert public_channel.size > 0
    assert public_channel.size == package_version.size

    assert package_version.package_name == public_package.name

    update_indexes(dao, pkgstore, public_channel.name)

    # Get package files
    package_filenames = [
        os.path.join(version.platform, version.filename)
        for version in public_package.package_versions  # type: ignore
    ]

    # Get repodata content
    package_dir = Path(pkgstore.channels_dir) / public_channel.name / 'linux-64'
    with open(package_dir / 'repodata.json', 'r') as fd:
        repodata = json.load(fd)

    # Check that all packages are initially in repodata
    for filename in package_filenames:
        assert os.path.basename(filename) in repodata["packages"].keys()

    # Get channel files
    init_files = sorted(pkgstore.list_files(public_channel.name))

    response = auth_client.delete(
        f"/api/channels/{public_channel.name}/packages/{public_package.name}"
    )

    assert response.status_code == 200

    db.refresh(public_channel)
    assert public_channel.size == 0

    versions = (
        db.query(PackageVersion)
        .filter(PackageVersion.package_name == public_package.name)
        .all()
    )

    assert len(versions) == 0

    # Check that repodata content has been updated
    with open(package_dir / 'repodata.json', 'r') as fd:
        repodata = json.load(fd)

    assert repodata["info"] == repodata["info"]

    # Remove package files from files list
    # Check that packages have been removed from repodata
    for filename in package_filenames:
        init_files.remove(filename)
        assert os.path.basename(filename) not in repodata["packages"]

    # Check that the package tree files is the same except for package files
    files = sorted(pkgstore.list_files(public_channel.name))

    assert files == init_files


def test_get_paginated_package_versions(
    auth_client, public_channel, package_version, dao
):
    response = auth_client.get(
        f"/api/paginated/channels/{public_channel.name}/"
        f"packages/{package_version.package_name}/versions"
    )

    assert response.status_code == 200
    assert isinstance(response.json().get('pagination'), dict)
    assert response.json().get('pagination').get('all_records_count') == 1

    assert isinstance(response.json().get('result'), list)
    assert len(response.json().get('result')) == 1


def test_get_package_version(auth_client, public_channel, package_version, dao):
    filename = "test-package-0.1-0.tar.bz2"
    platform = "linux-64"
    response = auth_client.get(
        f"/api/channels/{public_channel.name}/"
        f"packages/{package_version.package_name}/versions/{platform}/{filename}"
    )

    assert response.status_code == 200
    assert response.json()["filename"] == filename
    assert response.json()["platform"] == platform
    assert response.json()["download_count"] == 0


@pytest.mark.parametrize("user_server_role", [OWNER, MAINTAINER])
@pytest.mark.parametrize("user_package_role", [OWNER, MAINTAINER, MEMBER, None])
@pytest.mark.parametrize("user_channel_role", [OWNER, MAINTAINER, MEMBER, None])
@pytest.mark.parametrize("private", [True, False])
def test_get_package_version_permissions(
    auth_client,
    user,
    private_package_version,
    user_package_role,
    user_channel_role,
    private_channel,
    db,
    private_package,
    private,
    user_server_role,
):
    private_channel.private = private
    user.role = user_server_role

    if user_channel_role:
        channel_member = ChannelMember(
            channel=private_channel, user=user, role=user_channel_role
        )
        db.add(channel_member)
    if user_package_role:
        package_member = PackageMember(
            channel=private_channel,
            user=user,
            package=private_package,
            role=user_package_role,
        )
        db.add(package_member)
    db.commit()

    filename = private_package_version.filename
    platform = private_package_version.platform
    channel_name = private_package_version.channel_name
    package_name = private_package_version.package_name
    response = auth_client.get(
        f"/api/channels/{channel_name}/"
        f"packages/{package_name}/versions/{platform}/{filename}"
    )

    if not private:
        assert response.status_code == 200
    elif user_server_role in [OWNER, MAINTAINER]:
        assert response.status_code == 200
    elif user_channel_role in [OWNER, MAINTAINER, MEMBER]:
        assert response.status_code == 200
    elif user_package_role in [OWNER, MAINTAINER, MEMBER]:
        assert response.status_code == 200
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("user_server_role", [OWNER, MAINTAINER])
@pytest.mark.parametrize("user_package_role", [OWNER, MAINTAINER, MEMBER, None])
@pytest.mark.parametrize("user_channel_role", [OWNER, MAINTAINER, MEMBER, None])
@pytest.mark.parametrize("private", [True, False])
def test_delete_package_version_permissions(
    auth_client,
    user,
    private_package_version,
    user_package_role,
    user_channel_role,
    private_channel,
    db,
    private_package,
    pkgstore,
    private,
    user_server_role,
):
    private_channel.private = private
    user.role = user_server_role

    if user_channel_role:
        channel_member = ChannelMember(
            channel=private_channel, user=user, role=user_channel_role
        )
        db.add(channel_member)
    if user_package_role:
        package_member = PackageMember(
            channel=private_channel,
            user=user,
            package=private_package,
            role=user_package_role,
        )
        db.add(package_member)
    db.commit()

    filename = private_package_version.filename
    platform = private_package_version.platform
    channel_name = private_package_version.channel_name
    package_name = private_package_version.package_name
    response = auth_client.delete(
        f"/api/channels/{channel_name}/"
        f"packages/{package_name}/versions/{platform}/{filename}"
    )

    if user_server_role in [OWNER, MAINTAINER]:
        assert response.status_code == 200
    elif user_channel_role in [OWNER, MAINTAINER]:
        assert response.status_code == 200
    elif user_package_role in [OWNER, MAINTAINER]:
        assert response.status_code == 200
    else:
        assert response.status_code == 403


def test_get_non_existing_package_version(
    auth_client, public_channel, package_version, dao
):
    filename = "test-package-0.2-0.tar.bz2"
    platform = "linux-64"
    response = auth_client.get(
        f"/api/channels/{public_channel.name}/"
        f"packages/test-package/versions/{platform}/{filename}"
    )

    assert response.status_code == 404


@pytest.fixture
def remove_package_versions(db):
    yield
    db.query(PackageVersion).delete()


@pytest.mark.parametrize("package_name", ["test-package", "my-package"])
def test_upload_package_version(
    auth_client,
    public_channel,
    public_package,
    package_name,
    db,
    config,
    remove_package_versions,
):
    pkgstore = config.get_package_store()

    package_filename = "test-package-0.1-0.tar.bz2"
    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/packages/"
            f"{public_package.name}/files/",
            files=files,
        )

    with open(package_filename, "rb") as fid:
        condainfo = CondaInfo(fid, package_filename)
        condainfo._parse_conda()

    package_dir = Path(pkgstore.channels_dir) / public_channel.name / 'linux-64'

    if package_name == "my-package":
        assert response.status_code == 400
        detail = response.json()['detail']
        assert "package endpoint" in detail
        assert "does not match" in detail
        assert "test-package" in detail
        assert "my-package" in detail
        assert package_filename not in os.listdir(package_dir)
    else:
        assert response.status_code == 201
        db.refresh(public_channel)
        assert public_channel.size == condainfo.info['size']
        assert pkgstore.serve_path(
            public_channel.name, str(Path(condainfo.info['subdir']) / package_filename)
        )
        assert package_filename in os.listdir(package_dir)


def _upload_file_1(
    auth_client,
    public_channel,
    public_package,
    filepath: Path,
    force: bool = False,
):
    """Upload a file using /channels/{channel_name}/packages/{package_name}/files/"""
    with open(filepath, "rb") as fid:
        files = {"files": (filepath.name, fid)}
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/packages/"
            f"{public_package.name}/files/",
            files=files,
            data={"force": force},
        )
    return response


def _upload_file_2(
    auth_client,
    public_channel,
    public_package,
    filepath: Path,
    force: bool = False,
):
    """Upload a file using /channels/{channel_name}/upload/{file_name}"""

    with open(filepath, "rb") as fid:
        body_bytes = fid.read()
    response = auth_client.post(
        f"/api/channels/{public_channel.name}/upload/{filepath.name}",
        content=body_bytes,
        params={"force": force, "sha256": hashlib.sha256(body_bytes).hexdigest()},
    )
    return response


@pytest.mark.parametrize("upload_function", [_upload_file_1, _upload_file_2])
def test_upload_package_version_wrong_filename(
    auth_client,
    public_channel,
    public_package,
    package_name,
    db,
    config,
    remove_package_versions,
    upload_function: Callable,
):
    pkgstore = config.get_package_store()

    package_filename = "my-package-0.1-0.tar.bz2"
    os.rename("test-package-0.1-0.tar.bz2", package_filename)

    response = upload_function(
        auth_client, public_channel, public_package, Path(package_filename)
    )

    package_dir = Path(pkgstore.channels_dir) / public_channel.name / 'linux-64'

    assert response.status_code == 400
    detail = response.json()['detail']
    assert "info file" in detail
    assert "do not match" in detail
    assert "my-package" in detail
    assert not os.path.exists(package_dir)


def sha_and_md5(path: Union[Path, str]) -> Tuple[str, str]:
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(2**16), b""):
            sha.update(chunk)
            md5.update(chunk)
    return sha.hexdigest(), md5.hexdigest()


@pytest.mark.parametrize("upload_function", [_upload_file_1, _upload_file_2])
@pytest.mark.parametrize("package_name", ["test-package"])
def test_upload_duplicate_package_version(
    auth_client,
    public_channel,
    public_package,
    package_name,
    db,
    config,
    remove_package_versions,
    upload_function: Callable,
    tmp_path,
):
    pkgstore = config.get_package_store()

    def get_repodata():
        """Helper function to read repo data"""
        package_dir = Path(pkgstore.channels_dir) / public_channel.name / 'linux-64'
        return json.loads((package_dir / 'repodata.json').read_text())

    # Test setup: path1 is a package we will upload
    path1 = Path(__file__).parent.parent / "data" / "test-package-0.1-0.tar.bz2"

    # To test duplicate uploads, we have a second file `_copy`, which is the same
    # package and version but has a different content, so different hashes
    # We must move this file to a temporary directory so that we can give it the same
    # name as the first file.
    path2 = tmp_path / path1.name
    shutil.copyfile(
        Path(__file__).parent.parent / "data" / "test-package-0.1-0_copy.tar.bz2", path2
    )

    # Sanity checks
    sha1, md51 = sha_and_md5(path1)
    sha2, md52 = sha_and_md5(path2)
    assert (sha1 != sha2) and (
        md51 != md52
    ), "Sanity check failure: Test files have same hash"
    assert (
        path1.name == path2.name
    ), "Sanity check failure: Test files have different name"

    size1 = os.path.getsize(path1)
    size2 = os.path.getsize(path2)
    assert (
        size1 != size2
    ), "Sanity check failure: Test files must have different sizes for this test."

    # First upload
    # File should not exist
    assert not pkgstore.file_exists(public_channel.name, f"linux-64/{path1.name}")
    response = upload_function(auth_client, public_channel, public_package, path1)

    # Expect success
    assert response.status_code == 201

    # Check meta data is OK
    repodata_after_first = get_repodata()
    assert repodata_after_first["packages"][path1.name]["sha256"] == sha1
    assert repodata_after_first["packages"][path1.name]["md5"] == md51
    assert repodata_after_first["packages"][path1.name]["size"] == size1

    # Check that the file in the store is OK
    file_in_store = (
        Path(pkgstore.channels_dir) / public_channel.name / 'linux-64' / path1.name
    )
    assert size1 == os.path.getsize(file_in_store)
    assert (sha1, md51) == sha_and_md5(file_in_store)

    # Second upload: File with same name but different content, without force
    response = upload_function(auth_client, public_channel, public_package, path2)

    # Expect 409 since the file already exists
    assert response.status_code == 409
    detail = response.json()['detail']
    assert "Duplicate" in detail

    # Check meta data is OK: It should not have changed with respect to before
    repodata_after_second = get_repodata()
    assert repodata_after_second == repodata_after_first

    # Check that the file in the store is OK
    file_in_store = (
        Path(pkgstore.channels_dir) / public_channel.name / 'linux-64' / path1.name
    )

    # File in store should  not be the second file
    assert not (
        (sha2, md52) == sha_and_md5(file_in_store)
    ), "Duplicate upload without force updated stored file."
    assert not (
        size2 == os.path.getsize(file_in_store)
    ), "Duplicate upload without force updated stored file."

    # File in store should be the first file
    assert size1 == os.path.getsize(
        file_in_store
    ), "Duplicate upload without force updated stored file."
    assert (sha1, md51) == sha_and_md5(
        file_in_store
    ), "Duplicate upload without force updated stored file."

    # Third upload: Same as second but now with force
    # Ensure the 'time_modified' value changes in repodata.json
    time.sleep(1)

    # Submit the same package with 'force' flag
    response = upload_function(
        auth_client, public_channel, public_package, path2, force=True
    )
    assert response.status_code == 201

    # Check that repodata content has been updated
    repodata_after_force = get_repodata()

    # Info should match
    assert repodata_after_first["info"] == repodata_after_force["info"]

    # Package keys should match
    assert (
        repodata_after_first["packages"].keys()
        == repodata_after_force["packages"].keys()
    )

    # Hashes should now have changed to the second file
    assert repodata_after_force["packages"][path1.name]["sha256"] == sha2
    assert repodata_after_force["packages"][path1.name]["md5"] == md52
    assert repodata_after_force["packages"][path1.name]["size"] == size2

    assert (
        repodata_after_force["packages"][path1.name]["time_modified"]
        > repodata_after_first["packages"][path1.name]["time_modified"]
    )


@pytest.mark.parametrize("package_name", ["test-package"])
def test_check_channel_size_limits(
    auth_client, public_channel, public_package, db, config
):
    public_channel.size_limit = 0
    db.commit()
    pkgstore = config.get_package_store()

    package_filename = "test-package-0.1-0.tar.bz2"
    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/packages/"
            f"{public_package.name}/files/",
            files=files,
        )

    assert response.status_code == 422
    detail = response.json()['detail']
    assert "quota" in detail
    with pytest.raises(FileNotFoundError):
        pkgstore.serve_path(
            public_channel.name, str(Path("linux-64") / package_filename)
        )


def test_delete_package_version(
    auth_client, public_channel, package_version, dao, pkgstore, db
):
    assert public_channel.size > 0
    assert public_channel.size == package_version.size

    filename = "test-package-0.1-0.tar.bz2"
    platform = "linux-64"

    update_indexes(dao, pkgstore, public_channel.name)

    # Get repodata content and check that package is inside
    package_dir = Path(pkgstore.channels_dir) / public_channel.name / 'linux-64'
    with open(package_dir / 'repodata.json', 'r') as fd:
        repodata = json.load(fd)
    assert filename in repodata["packages"].keys()

    response = auth_client.delete(
        f"/api/channels/{public_channel.name}/"
        f"packages/{package_version.package_name}/versions/{platform}/{filename}"
    )

    assert response.status_code == 200

    versions = (
        db.query(PackageVersion)
        .filter(PackageVersion.package_name == package_version.package_name)
        .all()
    )

    assert len(versions) == 0

    with pytest.raises(Exception):
        pkgstore.serve_path(public_channel.name, str(Path(platform) / filename))

    db.refresh(public_channel)
    assert public_channel.size == 0

    # Check that repodata content has been updated
    with open(package_dir / 'repodata.json', 'r') as fd:
        repodata = json.load(fd)
    assert filename not in repodata["packages"].keys()


def test_package_name_length_limit(auth_client, public_channel, db):
    package_name = "package_" * 100

    response = auth_client.post(
        f"/api/channels/{public_channel.name}/packages", json={"name": package_name}
    )

    assert response.status_code == 201

    pkg = db.query(Package).filter(Package.name == package_name).one_or_none()

    assert pkg is not None


def test_validate_package_names(auth_client, public_channel, remove_package_versions):
    valid_package_names = [
        "interesting-package",
        "valid.package.name",
        "valid-package-name",
        "valid_package_name",
        "validpackage1234",
    ]

    for package_name in valid_package_names:
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/packages", json={"name": package_name}
        )

        assert response.status_code == 201

    invalid_package_names = [
        "InvalidPackage",  # no uppercase
        "invalid%20package",  # no spaces
        "invalid package",  # no spaces
        "invalid%package",  # no special characters
        "**invalidpackage**",
        "błędnypakiet",  # no unicode
    ]

    for package_name in invalid_package_names:
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/packages", json={"name": package_name}
        )
        assert response.status_code == 422


@pytest.mark.parametrize(
    "package_name,msg",
    [
        ("TestPackage", "String should match"),
        ("test-package", None),
    ],
)
def test_validate_package_names_files_endpoint(
    auth_client,
    public_channel,
    mocker,
    package_name,
    msg,
    config: Config,
    remove_package_versions,
):
    pkgstore = config.get_package_store()

    package_filename = "test-package-0.1-0.tar.bz2"

    with open(package_filename, "rb") as fid:
        condainfo = CondaInfo(fid, package_filename)
        condainfo._parse_conda()

    # patch conda info
    condainfo.info['name'] = package_name
    condainfo.channeldata['packagename'] = package_name

    mocked_cls = mocker.patch("quetz.main.CondaInfo")
    mocked_cls.return_value = condainfo

    with open(package_filename, "rb") as fid:
        files = {"files": (f"{package_name}-0.1-0.tar.bz2", fid)}
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/files/", files=files
        )

    if msg:
        assert response.status_code == 422
        assert msg in response.json()["detail"]

        with pytest.raises(FileNotFoundError):
            pkgstore.serve_path(
                public_channel.name, f'linux-64/{package_name}-0.1-0.tar.bz2'
            )
    else:
        assert response.status_code == 201
        assert pkgstore.serve_path(
            public_channel.name, f'linux-64/{package_name}-0.1-0.tar.bz2'
        )


@pytest.fixture
def plugin(app):
    from quetz.main import pm

    class Plugin:
        @hookimpl
        def validate_new_package(
            self,
            channel_name: str,
            package_name: str,
            file_handler: BinaryIO,
            condainfo: CondaInfo,
        ):
            raise ValidationError(f"name {package_name} not allowed")

    plugin = Plugin()
    pm.register(plugin)
    yield plugin
    pm.unregister(plugin)


def test_validation_hook(auth_client, public_channel, plugin, config):
    pkgstore = config.get_package_store()

    response = auth_client.post(
        f"/api/channels/{public_channel.name}/packages", json={"name": "package-name"}
    )

    assert response.status_code == 422
    assert "package-name not allowed" in response.json()["detail"]

    package_filename = "test-package-0.1-0.tar.bz2"
    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/files/", files=files
        )

    assert response.status_code == 422
    assert "test-package not allowed" in response.json()["detail"]
    with pytest.raises(FileNotFoundError):
        pkgstore.serve_path(public_channel.name, 'linux-64/test-package-0.1-0.tar.bz2')


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/channels/{channel_name}/packages/{package_name}",
        "/api/channels/{channel_name}/packages",
        "/api/packages/search/?q='channel:{channel_name}'",
    ],
)
@pytest.mark.parametrize("package_name", ["test-package"])
def test_package_current_version(
    auth_client, make_package_version, channel_name, endpoint
):
    # test platforms, current_version and url
    make_package_version("test-package-0.1-0.tar.bz2", "0.1", platform="linux-64")
    v1n = make_package_version("test-package-0.1-0.tar.bz2", "0.1", platform="noarch")
    v2l = make_package_version("test-package-0.2-0.tar.bz2", "0.2", platform="linux-64")
    v2o = make_package_version("test-package-0.2-0.tar.bz2", "0.2", platform="os-x")

    response = auth_client.get(
        endpoint.format(channel_name=channel_name, package_name=v2o.package_name)
    )
    assert response.status_code == 200

    package_data = response.json()
    if isinstance(package_data, list):
        assert len(package_data) == 1
        package_data = package_data[0]
    assert package_data['current_version'] == v2o.version

    # delete v0.2 os-x and linux-64 package
    response = auth_client.delete(
        f"/api/channels/{channel_name}/"
        f"packages/{v2o.package_name}/versions/{v2o.platform}/{v2o.filename}"
    )
    assert response.status_code == 200
    response = auth_client.delete(
        f"/api/channels/{channel_name}/"
        f"packages/{v2l.package_name}/versions/{v2l.platform}/{v2l.filename}"
    )
    assert response.status_code == 200

    # require current version to be 0.1
    response = auth_client.get(
        endpoint.format(channel_name=channel_name, package_name=v1n.package_name)
    )
    assert response.status_code == 200

    package_data = response.json()
    if isinstance(package_data, list):
        assert len(package_data) == 1
        package_data = package_data[0]
    assert package_data['current_version'] == v1n.version


@pytest.mark.parametrize("package_name", ["test-package"])
def test_get_package_with_versions(
    make_package_version, channel_name, dao, package_name
):
    # test loading of latest (current) and all other versions

    make_package_version("test-package-0.1-0.tar.bz2", "0.1", platform="linux-64")
    make_package_version("test-package-0.1-0.tar.bz2", "0.1", platform="noarch")
    v = make_package_version("test-package-0.2-0.tar.bz2", "0.2", platform="linux-64")

    package = dao.get_package(channel_name, package_name)

    assert package.current_package_version == v
    assert len(package.package_versions) == 3


@pytest.mark.parametrize("package_name", ["test-package"])
def test_package_channel_data_attributes(
    auth_client,
    make_package_version,
    channel_name,
    remove_package_versions,
):
    # test attributes derived from channel data
    for package_filename in Path(".").glob("*.tar.bz2"):
        with open(package_filename, "rb") as fid:
            files = {"files": (str(package_filename), fid)}
            response = auth_client.post(
                f"/api/channels/{channel_name}/files/",
                files=files,
            )

    response = auth_client.get(f"/api/channels/{channel_name}/packages/test-package")
    assert response.status_code == 200
    content = response.json()
    assert content['platforms'] == ['linux-64']
    assert content['url'].startswith("https://")


@pytest.fixture
def owner(db, dao: Dao):
    # create an owner with OWNER role
    owner = dao.create_user_with_role("owner", role=SERVER_OWNER)

    yield owner

    db.delete(owner)
    db.commit()


@pytest.fixture
def private_channel(db, dao: Dao, owner):
    # create a channel
    channel_data = Channel(name='private-channel', private=True)
    channel = dao.create_channel(channel_data, owner.id, "owner")

    yield channel

    db.delete(channel)
    db.commit()


@pytest.fixture
def private_package(db, owner, private_channel, dao):
    package_data = Package(name='test-package')

    package = dao.create_package(private_channel.name, package_data, owner.id, "owner")

    yield package

    db.delete(package)
    db.commit()


@pytest.fixture
def api_key(db, dao: Dao, owner, private_channel):
    # create an api key with restriction
    key = dao.create_api_key(
        owner.id,
        BaseApiKey.model_validate(
            dict(
                description="test api key",
                expire_at="2099-12-31",
                roles=[
                    {
                        'role': 'maintainer',
                        'package': None,
                        'channel': private_channel.name,
                    }
                ],
            )
        ),
        "API key with role restruction",
    )

    yield key

    # delete API Key
    key.deleted = True
    db.commit()


def test_upload_package_with_api_key(client, dao: Dao, owner, private_channel, api_key):
    # set api key of the anonymous user 'owner_key' to headers
    client.headers['X-API-Key'] = api_key.key

    # post new package
    response = client.post(
        f"/api/channels/{private_channel.name}/packages",
        json={"name": "test-package", "summary": "none", "description": "none"},
    )
    assert response.status_code == 201

    # we used the anonymous user of the API key for upload,
    # but expect the owner to be the package owner
    member = dao.get_package_member(
        private_channel.name, 'test-package', username=owner.username
    )
    assert member


def test_upload_file_to_package_with_api_key(
    dao: Dao, client, owner, private_channel, private_package, api_key
):
    # set api key of the anonymous user 'owner_key' to headers
    client.headers['X-API-Key'] = api_key.key

    package_filename = "test-package-0.1-0.tar.bz2"
    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = client.post(
            f"/api/channels/{private_channel.name}/packages/"
            f"{private_package.name}/files/",
            files=files,
        )
        assert response.status_code == 201

    # we used the anonymous user of the API key for upload,
    # but expect the owner to be the package owner
    version = dao.get_package_version_by_filename(
        channel_name=private_channel.name,
        package_name=private_package.name,
        filename=package_filename,
        platform='linux-64',
    )
    assert version
    assert version.uploader == owner


def test_upload_file_to_channel_with_api_key(
    dao: Dao, client, owner, private_channel, api_key
):
    # set api key of the anonymous user 'owner_key' to headers
    client.headers['X-API-Key'] = api_key.key

    package_filename = "test-package-0.1-0.tar.bz2"
    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = client.post(
            f"/api/channels/{private_channel.name}/files/",
            files=files,
        )
        assert response.status_code == 201

    # we used the anonymous user of the API key for upload,
    # but expect the owner to be the package owner
    version = dao.get_package_version_by_filename(
        channel_name=private_channel.name,
        package_name='test-package',
        filename=package_filename,
        platform='linux-64',
    )
    assert version
    assert version.uploader == owner
