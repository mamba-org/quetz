from fastapi.testclient import TestClient


def test_get_health_ready(client: TestClient):
    response = client.get("/health/ready")
    assert response.status_code == 200


def test_get_health_live(client: TestClient):
    response = client.get("/health/live")
    assert response.status_code == 200
