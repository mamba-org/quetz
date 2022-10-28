from passlib.hash import pbkdf2_sha256
from quetz_sql_authenticator.api import _calculate_hash
from quetz_sql_authenticator.db_models import Credentials


def test_invalid_login(client, testuser, testpassword):
    response = client.post(
        "/auth/sql/authorize",
        data={"username": testuser, "password": testpassword},
    )
    # Unauthorized
    assert response.status_code == 200
    assert "login failed" in response.text


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


def test_create_user(owner_client, db, testuser, testpassword):
    # Check that user is not in table
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )

    response = owner_client.post(
        f"/api/sqlauth/credentials/{testuser}?password={testpassword}",
    )

    # Check that user is in table
    assert response.status_code == 200
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is not None
    )


def test_update_non_existing_user(owner_client, db, testuser, testpassword):
    # Check that user is not in table
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )

    response = owner_client.put(
        f"/api/sqlauth/credentials/{testuser}?password={testpassword}",
    )

    # Check that user is not in table
    assert response.status_code == 404
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )


def test_update_user(owner_client, db, testuser, testpassword):
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
    response = owner_client.put(
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
        .password_hash
    )

    assert pbkdf2_sha256.verify(newpassword, password_hash)


def test_delete_user(owner_client, db, testuser, testpassword):
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

    response = owner_client.delete(
        f"/api/sqlauth/credentials/{testuser}",
    )

    # Check that user is in table
    assert response.status_code == 200
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )


def test_delete_non_existing_user(owner_client, db, testuser, testpassword):
    # Check that user is not in table
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )

    response = owner_client.delete(
        f"/api/sqlauth/credentials/{testuser}",
    )

    # Check that user is not in table
    assert response.status_code == 404
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is None
    )


def test_get_all_users(owner_client, db, testuser, testpassword):
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

    response = owner_client.get(
        "/api/sqlauth/credentials",
    )

    # Check that user is in table
    assert response.status_code == 200
    assert testuser in response.text


def test_get_all_users_unauthorized(member_client):
    response = member_client.get(
        "/api/sqlauth/credentials",
    )

    assert response.status_code == 403
    assert "this operation requires owner or maintainer roles" in response.text


def test_double_create(owner_client, testuser, testpassword):
    response = owner_client.post(
        f"/api/sqlauth/credentials/{testuser}?password={testpassword}",
    )
    assert response.status_code == 200

    response = owner_client.post(
        f"/api/sqlauth/credentials/{testuser}?password={testpassword}",
    )
    assert response.status_code == 409


def test_changing_password(owner_client, client, db, testuser, testpassword):
    # Create user
    response = owner_client.post(
        f"/api/sqlauth/credentials/{testuser}?password={testpassword}",
    )
    assert response.status_code == 200

    # Assert user is in table
    assert (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
        is not None
    )

    # Test login
    response = client.post(
        "/auth/sql/authorize",
        data={"username": testuser, "password": testpassword},
    )
    # Assert that we get a redirect to the main page
    assert response.status_code == 303

    # Login in as owner again
    response = client.get("/api/dummylogin/test_owner")
    assert response.status_code == 200

    # Change password
    newpassword = "newpassword"
    response = owner_client.put(
        f"/api/sqlauth/credentials/{testuser}?password={newpassword}",
    )
    assert response.status_code == 200

    # Check password in table
    credentials = (
        db.query(Credentials).filter(Credentials.username == testuser).one_or_none()
    )
    assert pbkdf2_sha256.verify(newpassword, credentials.password_hash)

    # Test that old password does not work
    response = client.post(
        "/auth/sql/authorize",
        data={"username": testuser, "password": testpassword},
    )
    assert response.status_code == 200
    assert "login failed" in response.text

    # Test that new password works
    response = client.post(
        "/auth/sql/authorize",
        data={"username": testuser, "password": newpassword},
    )
    # Assert that we get a redirect to the main page
    assert response.status_code == 303
