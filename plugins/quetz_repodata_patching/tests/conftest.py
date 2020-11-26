from pytest import fixture

pytest_plugins = "quetz.testing.fixtures"


@fixture
def plugins():
    return ["quetz-repodata_patching"]
