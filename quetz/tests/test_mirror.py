from quetz.db_models import Channel


def test_mirror_url(db):
    """test configuring mirror url"""

    channel = Channel(name="mirror_channel", mirror_channel_url="http://host")
    db.add(channel)
    db.commit()
    
    found = db.query(Channel).first()

    assert found.mirror_channel_url == "http://host"

    db.delete(found)
    db.commit()

    channel = Channel(name="local_channel")
    db.add(channel)
    db.commit()

    found = db.query(Channel).first()
    
    assert not found.mirror_channel_url
