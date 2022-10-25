import pytest

pytest_plugins = "quetz.testing.fixtures"


@pytest.fixture
def plugins():
    return ["quetz-sql-authenticator"]
