import pytest

pytest_plugins = "quetz.testing.fixtures"


@pytest.fixture
def plugins():
    # defines plugins to enable for testing
    return ["quetz-dictauthenticator"]
