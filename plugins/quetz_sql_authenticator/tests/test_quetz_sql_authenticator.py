from passlib.hash import pbkdf2_sha256
from quetz_sql_authenticator.api import _calculate_hash
from quetz_sql_authenticator.db_models import Credentials


# Test invalid login
def test_invalid_login(client, testuser, testpassword):
    response = client.post(
        "/auth/sql/authorize",
        data={"username": testuser, "password": testpassword},
    )
    # Unauthorized
    assert response.status_code == 401
    assert "login failed" in response.text


# Test valid login
def test_valid_login(client, db, testuser, testpassword):
    # Insert user
    credentials = Credentials(
        username=testuser, password_hash=_calculate_hash(testpassword)
    )
    db.add(credentials)

    response = client.post(
        "/auth/sql/authorize",
        data={"username": testuser, "password": testpassword},
    )
    # Assert that we get a redirect to the main page
    assert response.status_code == 303


# Test create user
def test_create_user(client, db, testuser, testpassword):
    # Check that user is not in table
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )

    response = client.post(
        f"/api/sqlauth/credentials/{testuser}?password={testpassword}",
    )

    # Check that user is in table
    assert response.status_code == 200
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is not None
    )


def test_update_non_existing_user(client, db, testuser, testpassword):
    # Check that user is not in table
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )

    response = client.put(
        f"/api/sqlauth/credentials/{testuser}?password={testpassword}",
    )

    # Check that user is not in table
    assert response.status_code == 404
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )


def test_update_user(client, db, testuser, testpassword):
    # Insert user
    credentials = Credentials(
        username=testuser, password_hash=_calculate_hash(testpassword)
    )
    db.add(credentials)

    # Assert user is in table
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is not None
    )

    newpassword = "newpassword"
    response = client.put(
        f"/api/sqlauth/credentials/{testuser}?password={newpassword}",
    )

    # Check that user is in table
    assert response.status_code == 200
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is not None
    )
    password_hash = (
        db.query(Credentials)
        .filter(Credentials.username == testuser)
        .one_or_none()
        .password
    )

    assert pbkdf2_sha256.verify(newpassword, password_hash)


def test_delete_user(client, db, testuser, testpassword):
    # Insert user
    credentials = Credentials(
        username=testuser, password_hash=_calculate_hash(testpassword)
    )
    db.add(credentials)

    # Assert user is in table
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is not None
    )

    response = client.delete(
        f"/api/sqlauth/credentials/{testuser}",
    )

    # Check that user is in table
    assert response.status_code == 200
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )


def test_delete_non_existing_user(client, db, testuser, testpassword):
    # Check that user is not in table
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )

    response = client.delete(
        f"/api/sqlauth/credentials/{testuser}",
    )

    # Check that user is not in table
    assert response.status_code == 404
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )


def test_reset(client, db, testuser, testpassword):
    # Insert user
    credentials = Credentials(
        username=testuser, password_hash=_calculate_hash(testpassword)
    )
    db.add(credentials)

    # Assert user is in table
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is not None
    )

    response = client.post(
        "/api/sqlauth/reset",
    )

    # Check that user is not in table
    assert response.status_code == 200
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )
