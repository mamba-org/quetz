from pathlib import Path

import pytest

from quetz import hookimpl
from quetz.authorization import MAINTAINER, MEMBER, OWNER
from quetz.db_models import ChannelMember, Package, PackageMember, PackageVersion
from quetz.errors import ValidationError
from quetz.pkgstores import PackageStore


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


def test_delete_package_versions(
    auth_client, public_channel, public_package, package_version, dao, db, pkgstore
):

    assert package_version.package_name == public_package.name

    response = auth_client.delete(
        f"/api/channels/{public_channel.name}/packages/{public_package.name}"
    )

    assert response.status_code == 200

    versions = (
        db.query(PackageVersion)
        .filter(PackageVersion.package_name == public_package.name)
        .all()
    )

    assert len(versions) == 0

    files = pkgstore.list_files(public_channel.name)

    assert len(files) == 0


def test_get_package_version(auth_client, public_channel, package_version, dao):
    filename = "test-package-0.1-0.tar.bz2"
    platform = "linux-64"
    response = auth_client.get(
        f"/api/channels/{public_channel.name}/"
        f"packages/{package_version.package_name}/versions/{platform}/{filename}"
    )

    assert response.status_code == 200
    assert response.json()['filename'] == filename
    assert response.json()['platform'] == platform


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


def test_delete_package_version(
    auth_client, public_channel, package_version, dao, pkgstore: PackageStore, db
):
    filename = "test-package-0.1-0.tar.bz2"
    platform = "linux-64"
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


def test_package_name_length_limit(auth_client, public_channel, db):

    package_name = "package_" * 100

    response = auth_client.post(
        f"/api/channels/{public_channel.name}/packages", json={"name": package_name}
    )

    assert response.status_code == 201

    pkg = db.query(Package).filter(Package.name == package_name).one_or_none()

    assert pkg is not None


def test_validate_package_names(auth_client, public_channel):

    valid_package_names = [
        "interesting-package",
        "valid.package.name",
        "valid-package-name",
        "valid_package_name" "validpackage1234",
    ]

    for package_name in valid_package_names:
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/packages", json={"name": package_name}
        )

    assert response.status_code == 201

    invalid_package_names = [
        "InvalidPackage",
        "invalid%20package",
        "invalid package",
        "invalid%package",
        "**invalidpackage**",
        "błędnypakiet",
    ]

    for package_name in invalid_package_names:

        response = auth_client.post(
            f"/api/channels/{public_channel.name}/packages", json={"name": package_name}
        )
        assert response.status_code == 422


def test_validate_package_names_files_endpoint(auth_client, public_channel, mocker):

    mocked_condainfo = mocker.patch("quetz.main.CondaInfo")
    mocked_condainfo.return_value.info = {"name": "TestPackage"}

    package_filename = "test-package-0.1-0.tar.bz2"
    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/files/", files=files
        )

    assert response.status_code == 400


def test_validation_hook(auth_client, public_channel):
    from quetz.main import pm

    class Plugin:
        @hookimpl
        def validate_new_package_name(self, channel_name: str, package_name: str):
            raise ValidationError(f"name {package_name} not allowed")

    pm.register(Plugin())

    response = auth_client.post(
        f"/api/channels/{public_channel.name}/packages", json={"name": "package-name"}
    )

    assert response.status_code == 400
    assert "package-name not allowed" in response.json()['detail']

    package_filename = "test-package-0.1-0.tar.bz2"
    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/files/", files=files
        )

    assert response.status_code == 400
    assert "test-package not allowed" in response.json()['detail']
