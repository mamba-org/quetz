import json
import os
import time
from pathlib import Path
from typing import BinaryIO

import pytest

from quetz import hookimpl
from quetz.authorization import MAINTAINER, MEMBER, OWNER
from quetz.condainfo import CondaInfo
from quetz.config import Config
from quetz.db_models import ChannelMember, Package, PackageMember, PackageVersion
from quetz.errors import ValidationError
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


def test_upload_package_version_wrong_filename(
    auth_client,
    public_channel,
    public_package,
    package_name,
    db,
    config,
    remove_package_versions,
):
    pkgstore = config.get_package_store()

    package_filename = "my-package-0.1-0.tar.bz2"
    os.rename("test-package-0.1-0.tar.bz2", package_filename)
    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/packages/"
            f"{public_package.name}/files/",
            files=files,
        )

    package_dir = Path(pkgstore.channels_dir) / public_channel.name / 'linux-64'

    assert response.status_code == 400
    detail = response.json()['detail']
    assert "info file" in detail
    assert "do not match" in detail
    assert "my-package" in detail
    assert not os.path.exists(package_dir)


@pytest.mark.parametrize("package_name", ["test-package"])
def test_upload_duplicate_package_version(
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
    package_filename_copy = "test-package-0.1-0_copy.tar.bz2"

    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/packages/"
            f"{public_package.name}/files/",
            files=files,
        )

    # Get repodata content
    package_dir = Path(pkgstore.channels_dir) / public_channel.name / 'linux-64'
    with open(package_dir / 'repodata.json', 'r') as fd:
        repodata_init = json.load(fd)

    # Try submitting the same package without 'force' flag
    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/packages/"
            f"{public_package.name}/files/",
            files=files,
        )
    assert response.status_code == 409
    detail = response.json()['detail']
    assert "Duplicate" in detail

    # Change the archive to test force update
    os.remove(package_filename)
    os.rename(package_filename_copy, package_filename)

    # Ensure the 'time_modified' value change in repodata.json
    time.sleep(1)

    # Submit the same package with 'force' flag
    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/packages/"
            f"{public_package.name}/files/",
            files=files,
            data={"force": True},
        )

    assert response.status_code == 201

    # Check that repodata content has been updated
    with open(package_dir / 'repodata.json', 'r') as fd:
        repodata = json.load(fd)

    assert repodata_init["info"] == repodata["info"]
    assert repodata_init["packages"].keys() == repodata["packages"].keys()
    repodata_init_pkg = repodata_init["packages"][package_filename]
    repodata_pkg = repodata["packages"][package_filename]
    assert repodata_init_pkg["time_modified"] != repodata_pkg["time_modified"]
    assert repodata_init_pkg["md5"] != repodata_pkg["md5"]
    assert repodata_init_pkg["sha256"] != repodata_pkg["sha256"]


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
        ("TestPackage", "string does not match"),
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
