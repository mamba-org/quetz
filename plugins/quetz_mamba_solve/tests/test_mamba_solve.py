import pytest


@pytest.fixture
def plugins():
    return ["quetz-mamba_solve"]


def test_mamba_solve_endpoint(client):
    response = client.post(
        "/api/mamba/solve",
        json={
            "channels": ["conda-forge"],
            "subdir": "osx-64",
            "spec": ["xtensor>=0.21.0"],
        },
    )
    assert response.status_code == 200
    assert b"@EXPLICIT" in response.content
    assert response.content.startswith(b"# platform: osx-64")

    assert b"conda-forge/osx-64/libcxx-" in response.content
    assert b"conda-forge/osx-64/xtensor-" in response.content
