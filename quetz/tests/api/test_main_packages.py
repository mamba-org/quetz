from pathlib import Path

import pytest

from quetz.authorization import MAINTAINER, MEMBER, OWNER
from quetz.db_models import Package, PackageVersion
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
