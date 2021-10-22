import io

import pytest
from fastapi import HTTPException


@pytest.fixture
def plugins():
    return ["quetz-tos"]


def upload_tos(client):
    tos_filename = "tos.txt"
    tos_content = "demo tos"
    url = "/api/tos/upload"

    files_to_upload = {'tos_file': (tos_filename, io.StringIO(tos_content))}

    response = client.post(url, files=files_to_upload)
    return response


def test_tos_upload_by_member(client, member_user):
    response = client.get("/api/dummylogin/alice")
    assert response.status_code == 200

    response = upload_tos(client)
    assert response.status_code == 403
    assert response.json()['detail'] == [
        'To upload new Terms of Services you need to be a server owner.'
    ]


def test_tos_upload_by_owner(client, owner_user):
    response = client.get("/api/dummylogin/madhurt")
    assert response.status_code == 200

    response = upload_tos(client)
    assert response.status_code == 201
    assert response.content == b'null'


def test_get_tos(client, tos_file, tos):
    response = client.get('/api/tos')
    assert response.json()['filename'] == 'tos.txt'
    assert response.json()['content'] == 'demo tos'


def test_tos_sign(client, member_user, tos_file, tos):
    response = client.get("/api/dummylogin/alice")
    assert response.status_code == 200

    response = client.post('/api/tos/sign')
    assert response.status_code == 201
    assert response.content == b'"TOS signed for alice"'


def test_tos_already_signed(client, tos_sign):
    response = client.get("/api/dummylogin/alice")
    assert response.status_code == 200

    response = client.post('/api/tos/sign')
    assert response.status_code == 201
    assert b"TOS already signed for alice" in response.content


def test_check_additional_permissions_hook_with_owner(
    client, owner_user, tos, tos_file
):
    response = client.get("/api/dummylogin/madhurt")
    assert response.status_code == 200

    from quetz_tos import main

    owner_tos_check = main.check_additional_permissions(
        owner_user.id, owner_user.role
    )
    assert owner_tos_check is True


def test_check_additional_permissions_hook_with_member(
    client, member_user, tos, tos_file
):
    response = client.get("/api/dummylogin/alice")
    assert response.status_code == 200

    from quetz_tos import main

    with pytest.raises(HTTPException) as e:
        main.check_additional_permissions(
            member_user.id, member_user.role
        )
    assert "status_code=403" in str(e)
    assert "detail='terms of service is not signed for alice'" in str(e)


def test_check_additional_permissions_hook_with_member_signed(
    client, member_user, tos, tos_file, tos_sign
):
    response = client.get("/api/dummylogin/alice")
    assert response.status_code == 200

    from quetz_tos import main

    member_tos_check = main.check_additional_permissions(
        member_user.id, member_user.role
    )
    assert member_tos_check is True
