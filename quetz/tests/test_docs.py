def test_docs_endpoint(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers['Content-Type']


def test_openapi_endpoint(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "application/json" in response.headers['Content-Type']


def test_redoc_endpoint(client):
    response = client.get("/redoc")
    assert response.status_code == 200
    assert "text/html" in response.headers['Content-Type']
