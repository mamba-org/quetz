import os
import tarfile
import uuid

import pytest

from quetz.db_models import Channel, User


@pytest.fixture
def proxy_channel(db):

    channel = Channel(name="test_proxy_channel", mirror_channel_url="http://host")
    db.add(channel)
    db.commit()

    yield channel

    db.delete(channel)
    db.commit()


@pytest.fixture
def mirror_channel(db):

    channel = Channel(
        name="test_mirror_channel",
        mirror_channel_url="http://host",
        mirror_mode="mirror",
    )
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


def test_get_mirror_url(proxy_channel, local_channel, client):
    """test configuring mirror url"""

    response = client.get("/api/channels/{}".format(proxy_channel.name))

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
            self.status_code = 200

    class DummySession:
        def get(self, path, stream=False):
            files.append(path)
            return DummyResponse()

    app.dependency_overrides[get_remote_session] = DummySession

    yield files

    app.dependency_overrides.pop(get_remote_session)


def test_download_remote_file(client, user, dummy_repo):
    """Test downloading from cache."""
    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post(
        "/api/channels",
        json={
            "name": "proxy_channel",
            "private": False,
            "mirror_channel_url": "http://host",
        },
    )
    assert response.status_code == 201

    # download from remote server
    response = client.get("/channels/proxy_channel/test_file.txt")

    assert response.status_code == 200
    assert response.content == b"Hello world!"
    assert dummy_repo == [("http://host/test_file.txt")]

    dummy_repo.pop()

    assert dummy_repo == []

    # serve from cache
    response = client.get("/channels/proxy_channel/test_file.txt")

    assert response.status_code == 200
    assert response.content == b"Hello world!"

    assert dummy_repo == []

    # new file - download from remote
    response = client.get("/channels/proxy_channel/test_file_2.txt")

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
            "name": "proxy_channel_2",
            "private": False,
            "mirror_channel_url": "http://host",
        },
    )
    assert response.status_code == 201

    response = client.get("/channels/proxy_channel_2/repodata.json")
    assert response.status_code == 200
    assert response.content == b"Hello world!"

    response = client.get("/channels/proxy_channel_2/repodata.json")
    assert response.status_code == 200
    assert response.content == b"Hello world!"

    assert dummy_repo == [
        ("http://host/repodata.json"),
        ("http://host/repodata.json"),
    ]


def test_method_not_implemented_for_proxies(client, proxy_channel):

    response = client.post("/api/channels/{}/packages".format(proxy_channel.name))
    assert response.status_code == 405
    assert "not implemented" in response.json()["detail"]


def test_api_methods_for_mirror_channels(client, mirror_channel):
    """mirror-mode channels should have all standard API calls"""

    response = client.get("/api/channels/{}/packages".format(mirror_channel.name))
    assert response.status_code == 200
    assert not response.json()


@pytest.mark.parametrize(
    "repo_content,expected_paths",
    [
        # linux-64 subdir without packages
        (
            [b'{"subdirs": ["linux-64"]}', b'{"packages": {}}'],
            ["channeldata.json", "linux-64/repodata.json"],
        ),
        # empty repodata
        (
            [b'{"subdirs": ["linux-64"]}', b"{}"],
            ["channeldata.json", "linux-64/repodata.json"],
        ),
        # no subodirs
        ([b'{"subdirs": []}'], ["channeldata.json"]),
        # two arbitrary subdirs
        (
            [b'{"subdirs": ["some-arch-1", "some-arch-2"]}', b"{}", b"{}"],
            [
                "channeldata.json",
                "some-arch-1/repodata.json",
                "some-arch-2/repodata.json",
            ],
        ),
    ],
)
def test_mirror_initial_sync(client, dummy_repo, user, expected_paths):

    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    host = "http://mirror3_host"
    response = client.post(
        "/api/channels",
        json={
            "name": "mirror_channel_" + str(uuid.uuid4())[:10],
            "private": False,
            "mirror_channel_url": host,
            "mirror_mode": "mirror",
        },
    )
    assert response.status_code == 201

    assert dummy_repo == [os.path.join(host, p) for p in expected_paths]


empty_archive = b""


@pytest.mark.parametrize(
    "repo_content",
    [
        [
            b'{"subdirs": ["linux-64"]}',
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
        "http://mirror3_host/channeldata.json",
        "http://mirror3_host/linux-64/repodata.json",
        "http://mirror3_host/linux-64/my_package-0.1.tar.bz",
    ]


def test_mirror_unavailable_url(client, user, db):

    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    channel_name = "mirror_channel_" + str(uuid.uuid4())[:10]
    host = "http://fantasy_host"

    response = client.post(
        "/api/channels",
        json={
            "name": channel_name,
            "private": False,
            "mirror_channel_url": host,
            "mirror_mode": "mirror",
        },
    )

    assert response.status_code == 503
    assert "unavailable" in response.json()['detail']
    assert host in response.json()['detail']

    channel = db.query(Channel).filter_by(name=channel_name).first()

    assert channel is None
