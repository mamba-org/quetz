from contextlib import contextmanager
from unittest import mock

from click.testing import CliRunner
from quetz_sql_authenticator.cli import _create
from quetz_sql_authenticator.db_models import Credentials

# Test invalid login
# Test valid login


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
        # Check that user is in db
        assert (
            db.query(Credentials)
            .filter(Credentials.username == "testuser")
            .one_or_none()
            is not None
        )
