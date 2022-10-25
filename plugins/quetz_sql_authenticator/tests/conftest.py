import pytest

pytest_plugins = "quetz.testing.fixtures"


@pytest.fixture
def plugins():
    return ["quetz-sql-authenticator"]


@pytest.fixture
def testuser():
    return "testuser"


@pytest.fixture
def testpassword():
    return "testpassword"
