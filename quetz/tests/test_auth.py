import os
import shutil
import uuid

from quetz.db_models import ApiKey, Channel, ChannelMember, User

from .conftest import clear_all


def test_private_channels(db, client):

    keya = "akey"
    keyb = "bkey"

    usera = User(id=uuid.uuid4().bytes, username='usera')
    db.add(usera)
    userb = User(id=uuid.uuid4().bytes, username='userb')
    db.add(userb)
    db.commit()

    assert len(db.query(User).all()) == 2

    db.add(ApiKey(key=keya, user_id=usera.id, owner_id=usera.id))
    db.add(ApiKey(key=keyb, user_id=userb.id, owner_id=userb.id))
    db.commit()

    channel1 = Channel(name="testchannel", private=False)
    channel2 = Channel(name="privatechannel", private=True)

    channel_member = ChannelMember(channel=channel2, user=usera, role='OWNER')
    for el in [channel1, channel2, channel_member]:
        db.add(el)
    db.commit()

    response = client.get('/')
    assert len(response.text)
    response = client.get('/api/channels')

    response = client.get('/api/channels', headers={"X-Api-Key": keya})
    assert len(response.json()) == 2
    response = client.get('/api/channels', headers={"X-Api-Key": keyb})
    assert len(response.json()) == 1

    clear_all(db)


def test_private_channels_download(db, client):
    keya = "akey"
    keyb = "bkey"

    usera = User(id=uuid.uuid4().bytes, username='usera')
    db.add(usera)
    userb = User(id=uuid.uuid4().bytes, username='userb')
    db.add(userb)
    db.commit()

    db.add(ApiKey(key=keya, user_id=usera.id, owner_id=usera.id))
    db.add(ApiKey(key=keyb, user_id=userb.id, owner_id=userb.id))
    db.commit()

    channel0 = Channel(name="channel0", private=False)
    channel1 = Channel(name="channel1", private=True)

    channel_member0 = ChannelMember(channel=channel0, user=usera, role='member')
    channel_member1 = ChannelMember(channel=channel1, user=userb, role='member')
    for el in [channel0, channel1, channel_member0, channel_member1]:
        db.add(el)
    db.commit()

    os.makedirs('channels/channel0/noarch')
    os.makedirs('channels/channel1/noarch')

    with open("channels/channel0/noarch/current_repodata.json", "a") as f:
        f.write("file content 0")
    with open("channels/channel1/noarch/current_repodata.json", "a") as f:
        f.write("file content 1")

    # succeed on public channel
    response = client.get('/channels/channel0/noarch/current_repodata.json')
    assert response.status_code == 200
    assert response.text == "file content 0"

    # keep functioning when unnecessary token is provided
    response = client.get('/t/[api-key]/channels/channel0/noarch/current_repodata.json')
    assert response.status_code == 200
    assert response.text == "file content 0"

    # fail on private channel without credentials
    response = client.get('/channels/channel1/noarch/current_repodata.json')
    assert response.status_code == 401

    # fail on private channel with invalid credentials
    response = client.get(
        '/t/[invalid-api-key]/channels/channel1/noarch/current_repodata.json'
    )
    assert response.status_code == 401

    # fail on private channel with non member user
    response = client.get(f'/t/{keya}/channels/channel1/noarch/current_repodata.json')
    assert response.status_code == 403

    # succeed on private channel with member user
    response = client.get(f'/t/{keyb}/channels/channel1/noarch/current_repodata.json')
    assert response.status_code == 200
    assert response.text == "file content 1"

    clear_all(db)
    shutil.rmtree('channels')
