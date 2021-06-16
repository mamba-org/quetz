import os
import shutil
import uuid
from datetime import date
from unittest import mock
from urllib.parse import quote

from pytest import fixture

from quetz.authorization import Rules
from quetz.db_models import (
    ApiKey,
    Channel,
    ChannelMember,
    Package,
    PackageMember,
    PackageVersion,
    Profile,
    User,
)


class Data:
    def __init__(self, db):
        self.keya = "akey"
        self.keyb = "bkey"

        self.usera = User(id=uuid.uuid4().bytes, username='usera')
        Profile(name='usera', user=self.usera, avatar_url='')
        db.add(self.usera)

        self.userb = User(id=uuid.uuid4().bytes, username='userb')
        Profile(name='userb', user=self.userb, avatar_url='')
        db.add(self.userb)

        self.userc = User(id=uuid.uuid4().bytes, username='userc', role="owner")
        Profile(name='userc', user=self.userc, avatar_url='')
        db.add(self.userc)

        assert len(db.query(User).all()) == 3

        self.keya_obj = ApiKey(
            key=self.keya,
            time_created=date.today(),
            expire_at=date(2030, 1, 1),
            user_id=self.usera.id,
            owner_id=self.usera.id,
        )

        db.add(self.keya_obj)
        db.add(
            ApiKey(
                key=self.keyb,
                time_created=date.today(),
                expire_at=date(2030, 1, 1),
                user_id=self.userb.id,
                owner_id=self.userb.id,
            )
        )

        self.channel1 = Channel(name="testchannel", private=False)
        self.channel2 = Channel(name="privatechannel", private=True)

        self.package1 = Package(name="package1", channel=self.channel1)
        self.package2 = Package(name="package2", channel=self.channel2)

        self.package_version_1 = PackageVersion(
            id=uuid.uuid4().bytes,
            channel_name=self.channel1.name,
            package_name=self.package1.name,
            package_format='tarbz2',
            platform='noarch',
            version="0.0.1",
            build_number="0",
            build_string="",
            filename="filename.tar.bz2",
            info="{}",
            uploader_id=self.usera.id,
            size=101,
        )
        self.package_version_2 = PackageVersion(
            id=uuid.uuid4().bytes,
            channel_name=self.channel2.name,
            package_name=self.package2.name,
            package_format='tarbz2',
            platform='noarch',
            version="0.0.1",
            build_number="0",
            build_string="",
            filename="filename2.tar.bz2",
            info="{}",
            uploader_id=self.usera.id,
            size=101,
        )

        self.channel_member = ChannelMember(
            channel=self.channel2, user=self.usera, role='maintainer'
        )
        self.channel_member_userc = ChannelMember(
            channel=self.channel2, user=self.userc, role='owner'
        )

        self.package_member = PackageMember(
            channel=self.channel2, user=self.userc, package=self.package2, role="owner"
        )

        for el in [
            self.channel1,
            self.channel2,
            self.channel_member,
            self.channel_member_userc,
            self.package1,
            self.package2,
            self.package_version_1,
            self.package_version_2,
            self.package_member,
        ]:
            db.add(el)
        db.commit()

        self.db = db


@fixture
def channel_dirs(data, config):
    # need to use config to get the right workdir
    os.makedirs('channels/testchannel/noarch', exist_ok=True)
    os.makedirs('channels/privatechannel/noarch', exist_ok=True)

    with open("channels/testchannel/noarch/current_repodata.json", "a") as f:
        f.write("file content 0")
    with open("channels/privatechannel/noarch/current_repodata.json", "a") as f:
        f.write("file content 1")

    yield

    shutil.rmtree('channels')


@fixture
def data(db):
    data = Data(db)
    yield data


def test_private_channels(data, client):

    response = client.get('/')
    assert len(response.text)
    response = client.get('/api/channels')

    response = client.get('/api/channels', headers={"X-Api-Key": data.keya})
    assert len(response.json()) == 2
    assert {c['name'] for c in response.json()} == {
        c.name for c in [data.channel1, data.channel2]
    }

    response = client.get('/api/channels', headers={"X-Api-Key": data.keyb})
    assert len(response.json()) == 1
    assert response.json()[0]['name'] == data.channel1.name

    response = client.get('/api/channels')
    assert len(response.json()) == 1
    assert response.json()[0]['name'] == data.channel1.name

    # Channel #

    # public access to public channel
    response = client.get(f'/api/channels/{data.channel1.name}')
    assert response.status_code == 200
    assert ('name', data.channel1.name) in response.json().items()

    # public access to private channel
    response = client.get(f'/api/channels/{data.channel2.name}')
    assert response.status_code == 401

    # non-member credential access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}', headers={"X-Api-Key": data.keyb}
    )
    assert response.status_code == 403

    # member credential access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}', headers={"X-Api-Key": data.keya}
    )
    assert response.status_code == 200
    assert ('name', data.channel2.name) in response.json().items()

    # Packages #

    # public access to public channel
    response = client.get(f'/api/channels/{data.channel1.name}/packages')
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert ('name', data.package1.name) in response.json()[0].items()

    # public access to private channel
    response = client.get(f'/api/channels/{data.channel2.name}/packages')
    assert response.status_code == 401

    # non-member credential access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/packages', headers={"X-Api-Key": data.keyb}
    )
    assert response.status_code == 403

    # member credential access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/packages', headers={"X-Api-Key": data.keya}
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert ('name', data.package2.name) in response.json()[0].items()

    # Channel Members #

    # public access to public channel
    response = client.get(f'/api/channels/{data.channel1.name}/members')
    assert response.status_code == 401

    # public access to private channel
    response = client.get(f'/api/channels/{data.channel2.name}/members')
    assert response.status_code == 401

    # non-member credential access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/members', headers={"X-Api-Key": data.keyb}
    )
    assert response.status_code == 403

    # member credential access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/members', headers={"X-Api-Key": data.keya}
    )
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert ('role', data.channel_member.role) in response.json()[0].items()
    assert response.json()[0]['user']['id'] == str(uuid.UUID(bytes=data.usera.id))

    # Package #

    # public access to public channel
    response = client.get(
        f'/api/channels/{data.channel1.name}/packages/{data.package1.name}'
    )
    assert response.status_code == 200
    assert ('name', data.package1.name) in response.json().items()

    # public access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/packages/{data.package2.name}'
    )
    assert response.status_code == 401

    # non-member credential access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/packages/{data.package2.name}',
        headers={"X-Api-Key": data.keyb},
    )
    assert response.status_code == 403

    # member credential access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/packages/{data.package2.name}',
        headers={"X-Api-Key": data.keya},
    )
    assert response.status_code == 200
    assert ('name', data.package2.name) in response.json().items()

    # package Members #

    # public access to public channel
    response = client.get(
        f'/api/channels/{data.channel1.name}/packages/{data.package1.name}/members'
    )
    assert response.status_code == 200
    assert len(response.json()) == 0

    # public access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/packages/{data.package2.name}/members'
    )
    assert response.status_code == 401

    # non-member credential access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/packages/{data.package2.name}/members',
        headers={"X-Api-Key": data.keyb},
    )
    assert response.status_code == 403

    # member credential access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/packages/{data.package2.name}/members',
        headers={"X-Api-Key": data.keya},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1

    # package Versions #

    # public access to public channel
    response = client.get(
        f'/api/channels/{data.channel1.name}/packages/{data.package1.name}/versions'
    )
    assert response.status_code == 200
    assert len(response.json()) == 1

    # public access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/packages/{data.package2.name}/versions'
    )
    assert response.status_code == 401

    # non-member credential access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/packages/{data.package2.name}/versions',
        headers={"X-Api-Key": data.keyb},
    )
    assert response.status_code == 403

    # member credential access to private channel
    response = client.get(
        f'/api/channels/{data.channel2.name}/packages/{data.package2.name}/versions',
        headers={"X-Api-Key": data.keya},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1

    # Package Search #
    # query = f"channel:test -format:conda uploader:{data.usera.username}"
    query = "channel:test"
    query = quote(query)
    response = client.get(f'/api/packages/search/?q={query}')
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]['name'] == data.package1.name

    # query = f"format:conda platform:linux-64,noarch uploader:{data.userb.username}"
    # query = quote(query)
    # response = client.get(
    #     f'/api/packages/search/?q={query}', headers={"X-Api-Key": data.keyb}
    # )
    # assert response.status_code == 200
    # assert len(response.json()) == 0

    # query = f"-channel:{data.channel2.name} format:tarbz2,conda -platform:osx-64"
    query = f"-channel:{data.channel2.name}"
    query = quote(query)
    response = client.get(
        f'/api/packages/search/?q={query}', headers={"X-Api-Key": data.keyb}
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]['name'] == data.package1.name

    query = f"package NOT frame channel:{data.channel1.name},private"
    query = quote(query)
    response = client.get(
        f'/api/packages/search/?q={query}', headers={"X-Api-Key": data.keya}
    )
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert {c['name'] for c in response.json()} == {
        c.name for c in [data.package1, data.package2]
    }

    # Channel Search #
    query = "test private:no"
    query = quote(query)
    response = client.get(f'/api/channels/search/?q={query}')
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]['name'] == data.channel1.name

    query = "private:y"
    query = quote(query)
    response = client.get(f'/api/channels/search/?q={query}')
    assert response.status_code == 200
    assert len(response.json()) == 0

    query = "-private:false"
    query = quote(query)
    response = client.get(
        f'/api/channels/search/?q={query}', headers={"X-Api-Key": data.keya}
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]['name'] == data.channel2.name


def test_private_channels_create_package(data, client):
    # public access to public channel
    response = client.post(
        f'/api/channels/{data.channel1.name}/packages', '{"name": "newpackage1"}'
    )
    assert response.status_code == 401

    # public access to private channel
    response = client.post(
        f'/api/channels/{data.channel2.name}/packages', '{"name": "newpackage1"}'
    )
    assert response.status_code == 401

    # channel member can not create packages in public channel
    response = client.post(
        f'/api/channels/{data.channel1.name}/packages',
        json={"name": "newpackage2"},
        headers={"X-Api-Key": data.keyb},
    )
    assert response.status_code == 403

    # user with credentials to private channel
    response = client.post(
        f'/api/channels/{data.channel2.name}/packages',
        json={"name": "newpackage2"},
        headers={"X-Api-Key": data.keyb},
    )
    assert response.status_code == 403

    # member credential access to private channel
    response = client.post(
        f'/api/channels/{data.channel2.name}/packages',
        json={"name": "newpackage2"},
        headers={"X-Api-Key": data.keya},
    )
    assert response.status_code == 201


def test_private_channels_download(db, client, data, channel_dirs):

    # succeed on public channel
    response = client.get('/get/testchannel/noarch/current_repodata.json')
    assert response.status_code == 200
    assert response.text == "file content 0"

    # keep functioning when unnecessary token is provided
    response = client.get('/t/[api-key]/get/testchannel/noarch/current_repodata.json')
    assert response.status_code == 200
    assert response.text == "file content 0"

    # fail on private channel without credentials
    response = client.get('/get/privatechannel/noarch/current_repodata.json')
    assert response.status_code == 401

    # fail on private channel with invalid credentials
    response = client.get(
        '/t/[invalid-api-key]/get/privatechannel/noarch/current_repodata.json'
    )
    assert response.status_code == 401

    # fail on private channel with non member user
    response = client.get(
        f'/t/{data.keyb}/get/privatechannel/noarch/current_repodata.json'
    )
    assert response.status_code == 403

    # succeed on private channel with member user
    response = client.get(
        f'/t/{data.keya}/get/privatechannel/noarch/current_repodata.json'
    )
    assert response.status_code == 200
    assert response.text == "file content 1"


def test_create_api_key(data, client):

    response = client.get(f"/api/dummylogin/{data.userc.username}")
    assert response.status_code == 200

    response = client.post(
        '/api/api-keys',
        json={
            "description": "test-key",
            "roles": [{"channel": "privatechannel", "role": "member"}],
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "description": "test-key",
        'time_created': mock.ANY,
        'expire_at': None,
        "roles": [{"channel": "privatechannel", "role": "member", "package": None}],
        "key": mock.ANY,
    }

    # get key with package permissions

    response = client.post(
        '/api/api-keys',
        json={
            "description": "test-key",
            'expire_at': '2024-01-26',
            "roles": [
                {
                    "channel": "privatechannel",
                    "package": data.package2.name,
                    "role": "member",
                }
            ],
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "description": "test-key",
        'time_created': mock.ANY,
        'expire_at': '2024-01-26',
        "roles": [
            {
                "role": "member",
                "package": data.package2.name,
                "channel": "privatechannel",
            }
        ],
        "key": mock.ANY,
    }

    # get a key with user privileges

    response = client.post(
        '/api/api-keys',
        json={
            "description": "test-key",
            'expire_at': '2024-01-26',
            "roles": [],
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "description": "test-key",
        'time_created': mock.ANY,
        'expire_at': '2024-01-26',
        "roles": None,
        "key": mock.ANY,
    }


def test_use_wildcard_api_key_to_authenticate(data, client):

    response = client.get(f"/api/dummylogin/{data.userc.username}")
    assert response.status_code == 200

    response = client.post(
        '/api/api-keys',
        json={
            "description": "test-key",
            'expire_at': '2030-01-01',
            "roles": [],
        },
    )

    assert response.status_code == 201

    key = response.json()["key"]

    # per-channel key
    response = client.post(
        '/api/api-keys',
        json={
            "description": "test-key",
            'expire_at': '2030-01-01',
            "roles": [{"channel": "privatechannel", "role": "maintainer"}],
        },
    )

    assert response.status_code == 201
    channel_key = response.json()["key"]

    # add a new channel

    response = client.post(
        "/api/channels", json={"name": "my-new-channel", "private": True}
    )

    assert response.status_code == 201

    # clear session cookies
    client.cookies.clear()

    response = client.get(
        "/api/channels/privatechannel/members", headers={"X-API-Key": key}
    )

    assert response.status_code == 200

    response = client.get(
        "/api/channels/privatechannel/packages", headers={"X-API-Key": key}
    )
    assert response.status_code == 200

    response = client.get(
        "/api/channels/my-new-channel/members", headers={"X-API-Key": key}
    )

    assert response.status_code == 200

    response = client.get(
        "/api/channels/my-new-channel/packages", headers={"X-API-Key": key}
    )
    assert response.status_code == 200

    # using per-channel key

    response = client.get(
        "/api/channels/privatechannel/members", headers={"X-API-Key": channel_key}
    )

    assert response.status_code == 200

    response = client.get(
        "/api/channels/privatechannel/packages", headers={"X-API-Key": channel_key}
    )
    assert response.status_code == 200

    response = client.get(
        "/api/channels/my-new-channel/members", headers={"X-API-Key": channel_key}
    )

    assert response.status_code == 403

    response = client.get(
        "/api/channels/my-new-channel/packages", headers={"X-API-Key": channel_key}
    )
    assert response.status_code == 403


def test_authorizations_with_deleted_api_key(data: Data, db):

    auth = Rules(data.keya, {}, db)

    user_id = auth.get_user()

    assert user_id == data.usera.id

    data.keya_obj.deleted = True

    db.commit()

    user_id = auth.get_user()

    assert not user_id

    data.keya_obj.deleted = False


def test_authorizations_with_expired_api_key(data, client):

    response = client.get(f"/api/dummylogin/{data.userc.username}")
    assert response.status_code == 200

    response = client.post(
        '/api/api-keys',
        json={
            "description": "test-key",
            'expire_at': '2020-01-01',
            "roles": [],
        },
    )

    assert response.status_code == 201

    key = response.json()["key"]

    # clear session cookies
    client.cookies.clear()

    response = client.get(
        "/api/channels/privatechannel/members", headers={"X-API-Key": key}
    )

    assert response.status_code == 401


def test_authorizations_with_api_key_no_expiry(data, client, db):
    key = "noexpirykey"
    keya_obj = ApiKey(
        key=key,
        time_created=date.today(),
        expire_at=None,
        user_id=data.usera.id,
        owner_id=data.usera.id,
    )
    db.add(keya_obj)
    db.commit()

    response = client.get(
        f"/api/channels/{data.channel2.name}/members", headers={"X-API-Key": key}
    )

    assert response.status_code == 200
