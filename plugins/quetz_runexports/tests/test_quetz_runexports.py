pytest_plugins = "quetz.testing.fixtures"


def test_run_exports_endpoint(
    client, channel, package, package_version, package_runexports, db, session_maker
):
    version_id = f"{package_version.version}-{package_version.build_string}"

    response = client.get(
        f"/api/channels/{channel.name}/packages/{package.name}/versions/{version_id}/run_exports"  # noqa
    )
    assert response.status_code == 200
    assert response.json() == {"weak": ["somepackage > 3.0"]}
