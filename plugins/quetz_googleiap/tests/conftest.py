import pytest

pytest_plugins = "quetz.testing.fixtures"


@pytest.fixture
def plugins():
    # defines plugins to enable for testing
    return ['quetz-googleiap']

@pytest.fixture
def sqlite_in_memory():
    # use sqlite on disk so that we can modify it in a different process
    return False