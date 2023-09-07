def test_endpoint_docs(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers['Content-Type']
