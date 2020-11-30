def test_delete_package(auth_client, public_package):

    response = auth_client.delete(f"/api/packages{public_package.name}")

    assert response.status_code == 200
