def test_mamba_solve_endpoint(client):
    response = client.get("/api/mamba/solve/conda-forge/osx-64/xtensor>=0.21.0")
    assert response.status_code == 200
    assert (
        response.content
        == """# platform: osx-64

@EXPLICIT

https://conda.anaconda.org/conda-forge/osx-64/libcxx-11.1.0-habf9029_0.tar.bz2#a88609e545f948a404419c65cd96fa1a
https://conda.anaconda.org/conda-forge/osx-64/xtensor-0.23.4-h940c156_0.tar.bz2#4e01e80d87ddf3867715989f2d8cec7c
https://conda.anaconda.org/conda-forge/osx-64/xtl-0.7.2-h940c156_1.tar.bz2#57a0019a4f48cdd2f902cde9ca9d0fba"""  # noqa: E501
    )
