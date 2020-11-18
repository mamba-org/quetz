import os
import uuid
from io import BytesIO
from pathlib import Path

import pytest

from quetz import rest_models
from quetz.authorization import Rules
from quetz.db_models import Channel, Package, PackageVersion, User
from quetz.indexing import update_indexes
from quetz.mirror import (
    KNOWN_SUBDIRS,
    RemoteRepository,
    RemoteServerError,
    initial_sync_mirror,
)


@pytest.fixture
def proxy_channel(db):

    channel = Channel(
        name="test_proxy_channel", mirror_channel_url="http://host", mirror_mode="proxy"
    )
    db.add(channel)
    db.commit()

    yield channel

    db.delete(channel)
    db.commit()


@pytest.fixture
def mirror_channel(dao, user, db):

    channel_data = rest_models.Channel(
        name="test_mirror_channel",
        private=False,
        mirror_channel_url="http://host",
        mirror_mode="mirror",
    )

    channel = dao.create_channel(channel_data, user.id, "owner")

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


@pytest.fixture
def repo_content():
    return b"Hello world!"


@pytest.fixture
def status_code():
    return 200


@pytest.fixture
def dummy_response(repo_content, status_code):
    if isinstance(repo_content, list):
        repo_content = repo_content.copy()

    class DummyResponse:
        def __init__(self):
            if isinstance(repo_content, list):
                content = repo_content.pop(0)
            else:
                content = repo_content
            if isinstance(content, Path):
                with open(content.absolute(), "rb") as fid:
                    content = fid.read()
            self.raw = BytesIO(content)
            self.headers = {"content-type": "application/json"}
            if isinstance(status_code, list):
                self.status_code = status_code.pop(0)
            else:
                self.status_code = status_code

    return DummyResponse


@pytest.fixture
def dummy_repo(app, dummy_response):

    from quetz.main import get_remote_session

    files = []

    class DummySession:
        def get(self, path, stream=False):
            if path.startswith("http://fantasy_host"):
                raise RemoteServerError()
            files.append(path)
            return dummy_response()

    app.dependency_overrides[get_remote_session] = DummySession

    yield files

    app.dependency_overrides.pop(get_remote_session)


@pytest.fixture
def mirror_package(mirror_channel, db):
    pkg = Package(
        name="mirror_package", channel_name=mirror_channel.name, channel=mirror_channel
    )
    db.add(pkg)
    db.commit()

    yield pkg

    db.delete(pkg)
    db.commit()


def test_set_mirror_url(db, client, owner):
    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post(
        "/api/channels",
        json={
            "name": "test_create_channel",
            "private": False,
            "mirror_channel_url": "http://my_remote_host",
            "mirror_mode": "proxy",
        },
    )
    assert response.status_code == 201

    response = client.get("/api/channels/test_create_channel")

    assert response.status_code == 200
    assert response.json()["mirror_channel_url"] == "http://my_remote_host"


@pytest.mark.parametrize("mirror_mode", ["proxy", "mirror"])
@pytest.mark.parametrize(
    "user_role,expected_status",
    [("owner", 201), ("maintainer", 201), ("member", 403), (None, 403)],
)
def test_create_mirror_channel_permissions(
    client, user, user_role, db, expected_status, dummy_repo, mirror_mode
):

    db.query(User).filter(User.id == user.id).update({"role": user_role})

    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post(
        "/api/channels",
        json={
            "name": "test_create_channel",
            "private": False,
            "mirror_channel_url": "http://my_remote_host",
            "mirror_mode": mirror_mode,
        },
    )
    assert response.status_code == expected_status


def test_get_mirror_url(proxy_channel, local_channel, client):
    """test configuring mirror url"""

    response = client.get("/api/channels/{}".format(proxy_channel.name))

    assert response.status_code == 200
    assert response.json()["mirror_channel_url"] == "http://host"

    response = client.get("/api/channels/{}".format(local_channel.name))
    assert response.status_code == 200
    assert not response.json()["mirror_channel_url"]


@pytest.fixture
def package_version(user, mirror_channel, db, dao):
    # create package version that will added to local repodata
    package_format = "tarbz2"
    package_info = (
        '{"size": 5000, "sha256": "OLD-SHA", "md5": "OLD-MD5", "subdirs":["noarch"]}'
    )

    new_package_data = rest_models.Package(name="test-package")

    package = dao.create_package(
        mirror_channel.name,
        new_package_data,
        user_id=user.id,
        role="owner",
    )

    version = dao.create_version(
        mirror_channel.name,
        "test-package",
        package_format,
        "noarch",
        "0.1",
        "0",
        "",
        "test-package-0.1-0.tar.bz2",
        package_info,
        user.id,
    )
    yield version

    db.delete(package)
    db.delete(version)
    db.commit()


@pytest.fixture
def owner(user, db):
    user = db.query(User).get(user.id)
    user.role = "owner"
    db.commit()
    yield user


DUMMY_PACKAGE = Path("./test-package-0.1-0.tar.bz2")
DUMMY_PACKAGE_V2 = Path("./test-package-0.2-0.tar.bz2")


@pytest.mark.parametrize(
    "repo_content,arch,n_new_packages",
    [
        # different version (new SHA256)
        pytest.param(
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"sha256": "SHA"}}}',
                DUMMY_PACKAGE,
            ],
            "noarch",
            1,
            id="new-sha-sum",
        ),
        # no updates
        pytest.param(
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"sha256": "OLD-SHA"}}}',
                DUMMY_PACKAGE,
            ],
            "noarch",
            0,
            id="same-sha-sum",
        ),
        # package in a different subdir (different SHA)
        pytest.param(
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"sha256": "SHA"}}}',
                DUMMY_PACKAGE,
            ],
            "linux-64",
            1,
            id="new-subdir-and-new-sha",
        ),
        # package in a different subdir (same SHA)
        pytest.param(
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"sha256": "OLD-SHA"}}}',
                DUMMY_PACKAGE,
            ],
            "linux-64",
            1,
            id="new-subdir-old-sha",
        ),
        # new package name
        pytest.param(
            [
                b'{"packages": {"other-package-0.1-0.tar.bz2": {"sha256": "OLD-SHA"}}}',
                DUMMY_PACKAGE,
            ],
            "linux-64",
            1,
            id="new-package-name",
        ),
        # new version number
        pytest.param(
            [
                b'{"packages": {"test-package-0.2-0.tar.bz2": {"sha256": "SHA-V2"}}}',
                DUMMY_PACKAGE_V2,
            ],
            "noarch",
            1,
            id="new-version-number",
        ),
        # two new versions
        pytest.param(
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"sha256": "NEW-SHA"}, "other-package-0.2-0.tar.bz2": {"sha256": "OLD-SHA"}}}',  # noqa
                DUMMY_PACKAGE,
                DUMMY_PACKAGE_V2,
            ],
            "noarch",
            2,
            id="two-new-package-versions",
        ),
        # only one of the two is new
        pytest.param(
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"sha256": "OLD-SHA"}, "other-package-0.2-0.tar.bz2": {"sha256": "SHA-V2"}}}',  # noqa
                DUMMY_PACKAGE_V2,
            ],
            "noarch",
            1,
            id="two-packages-one-new",
        ),
        # only md5 checksum (new checksum)
        pytest.param(
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"md5": "NEW-MD5"}}}',
                DUMMY_PACKAGE,
            ],
            "noarch",
            1,
            id="new-md5-sum",
        ),
        # only md5 checksum (old checksum)
        pytest.param(
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"md5": "OLD-MD5"}}}',
                DUMMY_PACKAGE,
            ],
            "noarch",
            0,
            id="old-md5-sum",
        ),
        # check with sha256 first (new sha)
        pytest.param(
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"sha256": "OLD-SHA", "md5": "NEW-MD5"}}}',  # noqa
                DUMMY_PACKAGE,
            ],
            "noarch",
            0,
            id="old-sha-new-md5",
        ),
        # check with sha256 first (old sha)
        pytest.param(
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"sha256": "NEW-SHA", "md5": "OLD-MD5"}}}',  # noqa
                DUMMY_PACKAGE,
            ],
            "noarch",
            1,
            id="new-sha-old-md5",
        ),
        # no checksums, force update
        pytest.param(
            [
                b'{"packages": {"test-package-0.2-0.tar.bz2": {}}}',
                DUMMY_PACKAGE_V2,
            ],
            "noarch",
            1,
            id="no-checksums-force-update",
        ),
    ],
)
def test_synchronisation_sha(
    repo_content,
    mirror_channel,
    dao,
    config,
    dummy_response,
    db,
    user,
    n_new_packages,
    arch,
    package_version,
):
    pkgstore = config.get_package_store()
    rules = Rules("", {"user_id": str(uuid.UUID(bytes=user.id))}, db)

    class DummySession:
        def get(self, path, stream=False):
            return dummy_response()

    # generate local repodata.json
    update_indexes(dao, pkgstore, mirror_channel.name)

    dummy_repo = RemoteRepository("", DummySession())

    initial_sync_mirror(
        mirror_channel.name,
        dummy_repo,
        arch,
        dao,
        pkgstore,
        rules,
        skip_errors=False,
    )

    versions = (
        db.query(PackageVersion)
        .filter(PackageVersion.channel_name == mirror_channel.name)
        .all()
    )

    assert len(versions) == n_new_packages + 1


@pytest.mark.parametrize(
    "repo_content,timestamp_mirror_sync,expected_timestamp,new_package",
    [
        # package modified but no server timestamp set
        (
            [b'{"packages": {"my-package": {"time_modified": 100}}}', DUMMY_PACKAGE],
            0,
            100,
            True,
        ),
        # package modified with later timestamp
        (
            [b'{"packages": {"my-package": {"time_modified": 1000}}}', DUMMY_PACKAGE],
            100,
            1000,
            True,
        ),
        # package modified with earlier timestamp
        (
            [b'{"packages": {"my-package": {"time_modified": 100}}}', DUMMY_PACKAGE],
            1000,
            1000,
            False,
        ),
    ],
)
def test_synchronisation_timestamp(
    mirror_channel,
    dao,
    config,
    dummy_response,
    db,
    user,
    expected_timestamp,
    timestamp_mirror_sync,
    new_package,
):

    mirror_channel.timestamp_mirror_sync = timestamp_mirror_sync
    pkgstore = config.get_package_store()
    rules = Rules("", {"user_id": str(uuid.UUID(bytes=user.id))}, db)

    class DummySession:
        def get(self, path, stream=False):
            return dummy_response()

    dummy_repo = RemoteRepository("", DummySession())

    initial_sync_mirror(
        mirror_channel.name,
        dummy_repo,
        "linux-64",
        dao,
        pkgstore,
        rules,
        skip_errors=False,
    )

    channel = db.query(Channel).get(mirror_channel.name)
    assert channel.timestamp_mirror_sync == expected_timestamp

    if new_package:
        assert channel.packages[0].name == "test-package"
        db.delete(channel.packages[0])
        db.commit()
    else:
        assert not channel.packages


def test_download_remote_file(client, owner, dummy_repo):
    """Test downloading from cache."""
    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post(
        "/api/channels",
        json={
            "name": "proxy_channel",
            "private": False,
            "mirror_channel_url": "http://host",
            "mirror_mode": "proxy",
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


def test_always_download_repodata(client, owner, dummy_repo):
    """Test downloading from cache."""
    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post(
        "/api/channels",
        json={
            "name": "proxy_channel_2",
            "private": False,
            "mirror_channel_url": "http://host",
            "mirror_mode": "proxy",
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

    response = client.get(
        "/channels/{}/missing/path/file.json".format(mirror_channel.name),
    )
    assert response.status_code == 404
    assert "file.json not found" in response.json()["detail"]


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
def test_mirror_initial_sync(client, dummy_repo, owner, expected_paths):

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
            (
                b'{"packages": {"my_package-0.1.tar.bz": '
                b'{"subdir":"linux-64", "time_modified": 10}}}'
            ),
            empty_archive,
        ]
    ],
)
def test_wrong_package_format(client, dummy_repo, owner):

    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    channel_name = "mirror_channel_" + str(uuid.uuid4())[:10]

    response = client.post(
        "/api/channels",
        json={
            "name": channel_name,
            "private": False,
            "mirror_channel_url": "http://mirror3_host",
            "mirror_mode": "mirror",
        },
    )

    assert response.status_code == 201

    assert dummy_repo == [
        "http://mirror3_host/channeldata.json",
        "http://mirror3_host/linux-64/repodata.json",
        "http://mirror3_host/linux-64/my_package-0.1.tar.bz",
    ]

    # check if package was not added
    response = client.get(f"/api/channels/{channel_name}/packages")

    assert response.status_code == 200

    assert not response.json()


def test_mirror_unavailable_url(client, owner, db, dummy_repo):

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
    assert "unavailable" in response.json()["detail"]
    assert host in response.json()["detail"]

    channel = db.query(Channel).filter_by(name=channel_name).first()

    assert channel is None


@pytest.mark.parametrize("user_role", ["owner"])
@pytest.mark.parametrize(
    "mirror_mode,mirror_channel_url,error_msg",
    [
        ("proxy", None, "'mirror_channel_url' is undefined"),
        (None, "http://my-host", "'mirror_mode' is undefined"),
        ("undefined", "http://my-host", "not a valid enumeration member"),
        ("proxy", "my-host", "does not match"),
        ("proxy", "http://", "does not match"),
        ("proxy", "http:my-host", "does not match"),
        ("proxy", "hosthttp://my-host", "does not match"),
        (None, None, None),  # non-mirror channel
        ("proxy", "http://my-host", None),
        ("proxy", "https://my-host", None),
        ("mirror", "http://my-host", None),
        ("mirror", "http://my-host/me/url", None),
    ],
)
def test_validate_mirror_parameters(
    auth_client, user, dummy_repo, mirror_mode, mirror_channel_url, error_msg
):
    channel_name = "my-channel"

    response = auth_client.post(
        "/api/channels",
        json={
            "name": channel_name,
            "private": False,
            "mirror_channel_url": mirror_channel_url,
            "mirror_mode": mirror_mode,
        },
    )

    if error_msg:
        assert response.status_code == 422
        assert error_msg in response.json()["detail"][0]["msg"]
    else:
        assert response.status_code == 201


@pytest.mark.parametrize("user_role", ["maintainer"])
def test_write_methods_for_local_channels(auth_client, local_channel, db):

    response = auth_client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = auth_client.post(
        "/api/channels/{}/packages".format(local_channel.name),
        json={"name": "my_package"},
    )
    assert response.status_code == 201


def test_disabled_methods_for_mirror_channels(
    client, mirror_channel, mirror_package, user
):

    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post("/api/channels/{}/packages".format(mirror_channel.name))
    assert response.status_code == 405
    assert "not implemented" in response.json()["detail"]

    files = {"files": ("my_package-0.1.tar.bz", "dfdf")}
    response = client.post(
        "/api/channels/{}/files/".format(mirror_channel.name), files=files
    )
    assert response.status_code == 405
    assert "not implemented" in response.json()["detail"]

    response = client.post(
        "/api/channels/{}/packages/mirror_package/files/".format(mirror_channel.name),
        files=files,
    )
    assert response.status_code == 405
    assert "not implemented" in response.json()["detail"]


@pytest.mark.parametrize(
    "repo_content,status_code,expected_archs",
    [
        # no channeldata
        (b"", 404, KNOWN_SUBDIRS),
        # badly formatted channel data
        (b"<html></html>", 200, KNOWN_SUBDIRS),
        # no archs in channeldata
        (b"{}", 200, []),
        # custom architecture
        (b'{"subdirs":["wonder-arch"]}', 200, ["wonder-arch"]),
    ],
)
def test_repo_without_channeldata(owner, client, dummy_repo, expected_archs):

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

    assert dummy_repo[0] == "http://mirror3_host/channeldata.json"
    for arch in expected_archs:
        assert "http://mirror3_host/{}/repodata.json".format(arch) in dummy_repo
    assert len(dummy_repo) == len(expected_archs) + 1

    assert response.status_code == 201


def test_sync_mirror_channel(mirror_channel, user, client, dummy_repo):

    response = client.put(
        f"/api/channels/{mirror_channel.name}/actions", json={"action": "synchronize"}
    )

    assert response.status_code == 401

    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.put(
        f"/api/channels/{mirror_channel.name}/actions", json={"action": "synchronize"}
    )
    assert response.status_code == 200


def test_sync_local_channel(local_channel, user, client, dummy_repo):
    response = client.put(
        f"/api/channels/{local_channel.name}/actions", json={"action": "synchronize"}
    )

    assert response.status_code == 405
    assert "synchronize not allowed" in response.json()["detail"]

    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.put(
        f"/api/channels/{local_channel.name}/actions", json={"action": "synchronize"}
    )
    assert response.status_code == 405
    assert "synchronize not allowed" in response.json()["detail"]


def test_can_not_sync_proxy_and_local_channels(
    proxy_channel, local_channel, user, client
):

    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.put(f"/api/channels/{proxy_channel.name}")
    assert response.status_code == 405

    response = client.put(f"/api/channels/{local_channel.name}")
    assert response.status_code == 405
