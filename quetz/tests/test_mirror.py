import os
import tarfile
import tempfile
import uuid

import pytest

from quetz.db_models import Channel, User


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
def repo_content():
    return b"Hello world!"


@pytest.fixture
def dummy_repo(app, repo_content):
    from io import BytesIO

    from quetz.main import get_remote_session

    files = []

    class DummyResponse:
        def __init__(self):
            if isinstance(repo_content, list):
                content = repo_content.pop(0)
            else:
                content = repo_content
            self.raw = BytesIO(content)
            self.headers = {"content-type": "application/json"}

    class DummySession:
        def get(self, path, stream=False):
            files.append(path)
            return DummyResponse()

    app.dependency_overrides[get_remote_session] = DummySession

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
    assert dummy_repo == [("http://host/test_file.txt")]

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
    assert dummy_repo == [("http://host/test_file_2.txt")]


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
        ("http://host/repodata.json"),
        ("http://host/repodata.json"),
    ]


def test_method_not_implemented_for_mirrors(client, mirror_channel):

    response = client.post("/api/channels/{}/packages".format(mirror_channel.name))
    assert response.status_code == 405
    assert "not implemented" in response.json()["detail"]


@pytest.mark.parametrize('repo_content', [b'{"packages": {}}', b'{}'])
def test_mirror_initial_sync(client, dummy_repo, user):

    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post(
        "/api/channels",
        json={
            "name": "mirror_channel_" + str(uuid.uuid4())[:10],
            "private": False,
            "mirror_channel_url": "http://mirror3_host",
            "mirror_mode": "mirror",
        },
    )
    assert response.status_code == 201

    assert dummy_repo == ["http://mirror3_host/linux-64/repodata.json"]


empty_archive = b""


@pytest.mark.parametrize(
    'repo_content',
    [
        [
            b'{"packages": {"my_package-0.1.tar.bz": {"subdir":"linux-64"}}}',
            empty_archive,
        ]
    ],
)
def test_wrong_package_format(client, dummy_repo, user):

    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    with pytest.raises(tarfile.ReadError):
        response = client.post(
            "/api/channels",
            json={
                "name": "mirror_channel_" + str(uuid.uuid4())[:10],
                "private": False,
                "mirror_channel_url": "http://mirror3_host",
                "mirror_mode": "mirror",
            },
        )

    assert dummy_repo == [
        "http://mirror3_host/linux-64/repodata.json",
        "http://mirror3_host/linux-64/my_package-0.1.tar.bz",
    ]
