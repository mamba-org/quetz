from contextlib import contextmanager
from unittest import mock

from click.testing import CliRunner
from quetz_sql_authenticator.cli import _calculate_hash, _create, _delete, _reset
from quetz_sql_authenticator.db_models import Credentials


# Test invalid login
def test_invalid_login(client):
    response = client.post(
        "/auth/sql/authorize",
        data={"username": "testuser", "password": "testpassword"},
    )
    # Unauthorized
    assert response.status_code == 401
    assert "login failed" in response.text


# Test valid login
def test_valid_login(client, db):
    # Insert user
    credentials = Credentials(
        username="testuser", password=_calculate_hash("testpassword")
    )
    db.add(credentials)

    response = client.post(
        "/auth/sql/authorize",
        data={"username": "testuser", "password": "testpassword"},
    )
    # Assert that we get a redirect to the main page
    assert response.status_code == 303


# Test create user
def test_create_user(db):
    @contextmanager
    def get_db():
        yield db

    runner = CliRunner()
    with mock.patch("quetz_sql_authenticator.cli.get_db_manager", get_db):
        result = runner.invoke(_create, ["testuser", "testpassword"])
        assert result.exit_code == 0
        assert "INFO: User 'testuser' created successfully." in result.output
        # Check that user is in table
        assert (
            db.query(Credentials)
            .filter(Credentials.username == "testuser")
            .one_or_none()
            is not None
        )


# Test create user
# def test_create_user_api(client, db):
#     response = client.get(
#         f"/api/channels/a/b/conda-suggest"
#     )
#     print(response.url)
#     # Unauthorized
#     assert "login failed" in response.text

#     # Check that user is in table
#     assert (
#         db.query(Credentials)
#         .filter(Credentials.username == "testuser")
#         .one_or_none()
#         is not None
#     )


def test_sample_test(client):
    response = client.get(f"/api/hello")  # noqa
    assert response.status_code == 200


def test_delete_user(db):
    @contextmanager
    def get_db():
        yield db

    # Insert user
    credentials = Credentials(username="testuser", password="testpassword")
    db.add(credentials)

    # Assert user is in table
    assert (
        db.query(Credentials).filter(Credentials.username == "testuser").one_or_none()
        is not None
    )

    runner = CliRunner()
    with mock.patch("quetz_sql_authenticator.cli.get_db_manager", get_db):
        result = runner.invoke(_delete, ["testuser"])
        assert result.exit_code == 0
        assert "INFO: User 'testuser' successfully deleted." in result.output
        # Check that user is not in table
        assert (
            db.query(Credentials)
            .filter(Credentials.username == "testuser")
            .one_or_none()
            is None
        )


def test_reset(db):
    @contextmanager
    def get_db():
        yield db

    # Insert user
    credentials = Credentials(username="testuser", password="testpassword")
    db.add(credentials)

    # Assert user is in table
    assert (
        db.query(Credentials).filter(Credentials.username == "testuser").one_or_none()
        is not None
    )

    runner = CliRunner()
    with mock.patch("quetz_sql_authenticator.cli.get_db_manager", get_db):
        result = runner.invoke(_reset, input='Y\n')
        assert result.exit_code == 0
        assert "INFO: Table reset successful." in result.output
        # Check that credentials table is empty
        assert db.query(Credentials).count() == 0
