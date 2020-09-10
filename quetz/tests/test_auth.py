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
