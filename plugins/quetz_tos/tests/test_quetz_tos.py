import io

import pytest
from fastapi import HTTPException


@pytest.fixture
def plugins():
    return ["quetz-tos"]


def upload_tos_en(client):
    params = {'language': 'EN'}
    tos_en_filename = "tos_en.txt"
    tos_en_content = "demo tos"
    url = "/api/tos/upload"

    files_to_upload = {'tos_file': (tos_en_filename, io.StringIO(tos_en_content))}

    response = client.post(url, params=params, files=files_to_upload)
    return response


def upload_tos_fr(client):
    params = {'language': 'FR'}
    tos_fr_filename = "tos_fr.txt"
    tos_fr_content = "demo tos"
    url = "/api/tos/upload"

    files_to_upload = {'tos_file': (tos_fr_filename, io.StringIO(tos_fr_content))}

    response = client.post(url, params=params, files=files_to_upload)
    return response


def test_tos_en_upload_by_member(client, member_user):
    response = client.get("/api/dummylogin/alice")
    assert response.status_code == 200

    response = upload_tos_en(client)
    assert response.status_code == 403
    assert response.json()['detail'] == [
        'To upload new Terms of Services you need to be a server owner.'
    ]


def test_tos_fr_upload_by_member(client, member_user):
    response = client.get("/api/dummylogin/alice")
    assert response.status_code == 200

    response = upload_tos_fr(client)
    assert response.status_code == 403
    assert response.json()['detail'] == [
        'To upload new Terms of Services you need to be a server owner.'
    ]


def test_tos_en_upload_by_owner(client, owner_user):
    response = client.get("/api/dummylogin/madhurt")
    assert response.status_code == 200

    response = upload_tos_en(client)
    assert response.status_code == 201
    assert response.content == b'null'


def test_tos_fr_upload_by_owner(client, owner_user):
    response = client.get("/api/dummylogin/madhurt")
    assert response.status_code == 200

    response = upload_tos_fr(client)
    assert response.status_code == 201
    assert response.content == b'null'


def test_get_tos_en(client, tos_file, tos):
    # params = {'language': 'EN'}
    response = client.get('/api/tos?lang=EN')
    # response = client.get('/api/tos', params=params)
    print(response.json())
    assert response.json()['filename'] == 'tos_en.txt'
    assert response.json()['content'] == 'demo tos'

def test_get_tos_fr(client, tos_file, tos):
    
    # params = {'language': 'FR'}
    # response = client.get('/api/tos', params=params)
    response = client.get('/api/tos?lang=FR') 
    print(response.json())
    assert response.json()['filename'] == 'tos_fr.txt'
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
    db, client, owner_user, tos, tos_file
):
    response = client.get("/api/dummylogin/madhurt")
    assert response.status_code == 200

    from quetz_tos import main

    owner_tos_check = main.check_additional_permissions(
        db, owner_user.id, owner_user.role
    )
    assert owner_tos_check is True


def test_check_additional_permissions_hook_with_member(
    db, client, member_user, tos, tos_file
):
    response = client.get("/api/dummylogin/alice")
    assert response.status_code == 200

    from quetz_tos import main

    with pytest.raises(HTTPException) as e:
        main.check_additional_permissions(db, member_user.id, member_user.role)
    assert "status_code=403" in str(e)
    assert "detail='terms of service is not signed for alice'" in str(e)


def test_check_additional_permissions_hook_with_member_signed(
    db, client, member_user, tos, tos_file, tos_sign
):
    response = client.get("/api/dummylogin/alice")
    assert response.status_code == 200

    from quetz_tos import main

    member_tos_check = main.check_additional_permissions(
        db, member_user.id, member_user.role
    )
    assert member_tos_check is True
