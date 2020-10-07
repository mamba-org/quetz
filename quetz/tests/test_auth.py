import os
import shutil
import uuid

from pytest import fixture

from quetz.db_models import ApiKey, Channel, ChannelMember, Package, Profile, User


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

        assert len(db.query(User).all()) == 2

        db.add(ApiKey(key=self.keya, user_id=self.usera.id, owner_id=self.usera.id))
        db.add(ApiKey(key=self.keyb, user_id=self.userb.id, owner_id=self.userb.id))

        self.channel1 = Channel(name="testchannel", private=False)
        self.channel2 = Channel(name="privatechannel", private=True)

        self.package1 = Package(name="Package1", channel=self.channel1)
        self.package2 = Package(name="Package2", channel=self.channel2)

        self.channel_member = ChannelMember(
            channel=self.channel2, user=self.usera, role='member'
        )
        for el in [
            self.channel1,
            self.channel2,
            self.channel_member,
            self.package1,
            self.package2,
        ]:
            db.add(el)
        db.commit()

        self.db = db

    def cleanup(self):
        db = self.db
        db.rollback()
        db.delete(self.package1)
        db.delete(self.package2)
        db.delete(self.channel_member)
        db.delete(self.channel1)
        db.delete(self.channel2)
        db.delete(self.usera)
        db.delete(self.userb)
        db.commit()


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


@fixture(scope="module")
def data(db):
    data = Data(db)
    yield data
    data.cleanup()


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
    assert response.status_code == 200
    assert len(response.json()) == 0

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
    assert len(response.json()) == 1
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
    assert len(response.json()) == 0

    # package Versions #

    # public access to public channel
    response = client.get(
        f'/api/channels/{data.channel1.name}/packages/{data.package1.name}/versions'
    )
    assert response.status_code == 200
    assert len(response.json()) == 0

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
    assert len(response.json()) == 0

    # Search #
    response = client.get('/api/search/package')
    assert response.status_code == 200
    print(f'serach: {response.json()}')
    assert len(response.json()) == 1
    assert response.json()[0]['name'] == data.package1.name

    response = client.get('/api/search/package', headers={"X-Api-Key": data.keyb})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]['name'] == data.package1.name

    response = client.get('/api/search/package', headers={"X-Api-Key": data.keya})
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert {c['name'] for c in response.json()} == {
        c.name for c in [data.package1, data.package2]
    }


def test_private_channels_create_package(data, client):
    # public access to public channel
    response = client.post(
        f'/api/channels/{data.channel1.name}/packages', '{"name": "NewPackage1"}'
    )
    assert response.status_code == 401

    # public access to private channel
    response = client.post(
        f'/api/channels/{data.channel2.name}/packages', '{"name": "NewPackage1"}'
    )
    assert response.status_code == 401

    # user with credentials to public channel
    response = client.post(
        f'/api/channels/{data.channel1.name}/packages',
        '{"name": "NewPackage2"}',
        headers={"X-Api-Key": data.keyb},
    )
    assert response.status_code == 201

    # user with credentials to private channel
    response = client.post(
        f'/api/channels/{data.channel2.name}/packages',
        '{"name": "NewPackage2"}',
        headers={"X-Api-Key": data.keyb},
    )
    assert response.status_code == 403

    # member credential access to private channel
    response = client.post(
        f'/api/channels/{data.channel2.name}/packages',
        '{"name": "NewPackage2"}',
        headers={"X-Api-Key": data.keya},
    )
    assert response.status_code == 201


def test_private_channels_download(db, client, data, channel_dirs):
    # keya = "akey"
    # keyb = "bkey"

    # usera = User(id=uuid.uuid4().bytes, username='usera')
    # db.add(usera)
    # userb = User(id=uuid.uuid4().bytes, username='userb')
    # db.add(userb)
    # db.commit()

    # db.add(ApiKey(key=keya, user_id=usera.id, owner_id=usera.id))
    # db.add(ApiKey(key=keyb, user_id=userb.id, owner_id=userb.id))
    # db.commit()

    # channel0 = Channel(name="channel0", private=False)
    # channel1 = Channel(name="channel1", private=True)

    # channel_member0 = ChannelMember(channel=channel0, user=usera, role='member')
    # channel_member1 = ChannelMember(channel=channel1, user=userb, role='member')
    # for el in [channel0, channel1, channel_member0, channel_member1]:
    #    db.add(el)
    # db.commit()

    # succeed on public channel
    response = client.get('/channels/testchannel/noarch/current_repodata.json')
    assert response.status_code == 200
    assert response.text == "file content 0"

    # keep functioning when unnecessary token is provided
    response = client.get(
        '/t/[api-key]/channels/testchannel/noarch/current_repodata.json'
    )
    assert response.status_code == 200
    assert response.text == "file content 0"

    # fail on private channel without credentials
    response = client.get('/channels/privatechannel/noarch/current_repodata.json')
    assert response.status_code == 401

    # fail on private channel with invalid credentials
    response = client.get(
        '/t/[invalid-api-key]/channels/privatechannel/noarch/current_repodata.json'
    )
    assert response.status_code == 401

    # fail on private channel with non member user
    response = client.get(
        f'/t/{data.keyb}/channels/privatechannel/noarch/current_repodata.json'
    )
    assert response.status_code == 403

    # succeed on private channel with member user
    response = client.get(
        f'/t/{data.keya}/channels/privatechannel/noarch/current_repodata.json'
    )
    assert response.status_code == 200
    assert response.text == "file content 1"
