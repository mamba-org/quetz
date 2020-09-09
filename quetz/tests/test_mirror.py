from quetz.db_models import Channel, User
import uuid

from fastapi.testclient import TestClient


import os
import tempfile
import pytest


@pytest.fixture
def config():

    config_str = r"""
[github]
# Register the app here: https://github.com/settings/applications/new
client_id = "aaa"
client_secret = ""

[sqlalchemy]
database_url = "sqlite:///:memory:"

[session]
secret = "eWrkA6xpa7LTSSYUwZEEVoOU62501Ucf9lmLcgzTj1I="
https_only = false
"""

    path = tempfile.mkdtemp()
    config_path = os.path.join(path, "config.toml")
    with open(config_path, "w") as fid:
        fid.write(config_str)
    old_dir = os.curdir
    os.chdir(path)
    os.environ["QUETZ_CONFIG_FILE"] = config_path
    yield config_path
    os.chdir(old_dir)


@pytest.fixture
def app(config, db):
    from quetz.main import app, get_db

    app.dependency_overrides[get_db] = lambda: db
    return app


@pytest.fixture
def client(app):
    client = TestClient(app)
    return client


@pytest.fixture
def mirror_channel(db):

    channel = Channel(name="test_mirror_channel", mirror_channel_url="http://host")
    db.add(channel)
    db.commit()

    yield channel

    db.delete(channel)
    db.commit()


@pytest.fixture
def local_channel(db):

    channel = Channel(name="test_local_channel")
    db.add(channel)
    db.commit()

    yield channel

    db.delete(channel)
    db.commit()


def test_set_mirror_url(db, client, user):
    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post(
        "/api/channels",
        json={
            "name": "test_create_channel",
            "private": False,
            "mirror_channel_url": "http://my_remote_host",
        },
    )
    assert response.status_code == 201

    channel = db.query(Channel).get("test_create_channel")
    assert channel.mirror_channel_url == "http://my_remote_host"


def test_get_mirror_url(mirror_channel, local_channel, client):
    """test configuring mirror url"""

    response = client.get("/api/channels/{}".format(mirror_channel.name))

    assert response.status_code == 200
    assert response.json()["mirror_channel_url"] == "http://host"

    response = client.get("/api/channels/{}".format(local_channel.name))
    assert response.status_code == 200
    assert not response.json()["mirror_channel_url"]


@pytest.fixture
def user(db):
    user = User(id=uuid.uuid4().bytes, username="bartosz")
    db.add(user)
    db.commit()
    yield db
    db.delete(user)
    db.commit()


@pytest.fixture
def dummy_repo(app):
    from quetz.main import RemoteRepository

    files = []

    class DummyRepo(RemoteRepository):
        def open(self, path):
            files.append((self.host, path))
            yield b"Hello world!"

    app.dependency_overrides[RemoteRepository] = DummyRepo

    return files


def test_download_remote_file(client, user, dummy_repo):
    """Test downloading from cache."""
    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post(
        "/api/channels",
        json={
            "name": "mirror_channel",
            "private": False,
            "mirror_channel_url": "http://host",
        },
    )
    assert response.status_code == 201

    # download from remote server
    response = client.get("/channels/mirror_channel/test_file.txt")

    assert response.status_code == 200
    assert response.content == b"Hello world!"
    assert dummy_repo == [("http://host", "test_file.txt")]

    dummy_repo.pop()

    assert dummy_repo == []

    # serve from cache
    response = client.get("/channels/mirror_channel/test_file.txt")

    assert response.status_code == 200
    assert response.content == b"Hello world!"

    assert dummy_repo == []

    # new file - download from remote
    response = client.get("/channels/mirror_channel/test_file_2.txt")

    assert response.status_code == 200
    assert response.content == b"Hello world!"
    assert dummy_repo == [("http://host", "test_file_2.txt")]


def test_always_download_repodata(client, user, dummy_repo):
    """Test downloading from cache."""
    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post(
        "/api/channels",
        json={
            "name": "mirror_channel_2",
            "private": False,
            "mirror_channel_url": "http://host",
        },
    )
    assert response.status_code == 201

    response = client.get("/channels/mirror_channel_2/repodata.json")
    assert response.status_code == 200
    assert response.content == b"Hello world!"

    response = client.get("/channels/mirror_channel_2/repodata.json")
    assert response.status_code == 200
    assert response.content == b"Hello world!"

    assert dummy_repo == [
        ("http://host", "repodata.json"),
        ("http://host", "repodata.json"),
    ]


def test_method_not_implemented_for_mirrors(client, mirror_channel):

    response = client.post("/api/channels/{}/packages".format(mirror_channel.name))
    assert response.status_code == 405
    assert "not implemented" in response.json()["detail"]
