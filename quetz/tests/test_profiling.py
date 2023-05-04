def test_endpoint_profiling(client):
    response = client.get("/health/ready/?profile=true")
    assert response.status_code == 200
    assert "text/html" in response.headers['Content-Type']
