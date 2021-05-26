def test_conda_trust_endpoint(client):

    response = client.get("/api/conda_trust")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello world!"}
