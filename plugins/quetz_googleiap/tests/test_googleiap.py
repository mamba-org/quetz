import pytest


@pytest.mark.parametrize(
    "config_extra", ['[googleiam]\nserver_admin_emails=["test@tester.com"]']
)
def test_authentication(client, db):
    response = client.get("/api/me")
    assert response.status_code == 401

    # add headers
    headers = {
        'X-Goog-Authenticated-User-Email': 'accounts.google.com:someone@tester.com',
        'X-Goog-Authenticated-User-Id': 'accounts.google.com:someone@tester.com',
    }

    response = client.get("/api/me", headers=headers)
    assert response.status_code == 200

    # # check if channel was created
    # response = client.get("/api/channels", headers=headers)
    # assert response.status_code == 200
    # assert response.json()['channels'][0]['name'] == 'someone'
