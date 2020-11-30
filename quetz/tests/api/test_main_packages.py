from quetz.db_models import Package


def test_delete_package(auth_client, public_package, public_channel, dao, db):

    response = auth_client.delete(
        f"/api/channels/{public_channel.name}/packages/{public_package.name}"
    )

    assert response.status_code == 200

    package = (
        db.query(Package).filter(Package.name == public_package.name).one_or_none()
    )

    assert package is None
