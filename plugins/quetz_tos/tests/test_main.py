def test_tos_endpoint(client):

    response = client.get("/api/tos")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello world!"}
