import pytest

from quetz.authorization import MAINTAINER, MEMBER, OWNER
from quetz.db_models import Package, PackageVersion


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


def test_delete_package_version(
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
