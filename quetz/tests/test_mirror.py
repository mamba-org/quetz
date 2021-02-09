import json
import os
import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quetz import hookimpl, rest_models
from quetz.authorization import Rules
from quetz.condainfo import CondaInfo
from quetz.db_models import Channel, Package, PackageVersion, User
from quetz.tasks.indexing import update_indexes
from quetz.tasks.mirror import (
    KNOWN_SUBDIRS,
    RemoteRepository,
    RemoteServerError,
    create_packages_from_channeldata,
    create_versions_from_repodata,
    handle_repodata_package,
    initial_sync_mirror,
)


@pytest.fixture
def proxy_channel(db):

    channel = Channel(
        name="test-proxy-channel", mirror_channel_url="http://host", mirror_mode="proxy"
    )
    db.add(channel)
    db.commit()

    yield channel

    db.delete(channel)
    db.commit()


@pytest.fixture
def mirror_channel(dao, user, db):

    channel_data = rest_models.Channel(
        name="test-mirror-channel",
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

    channel = Channel(name="test-local-channel")
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

        def close(self):
            pass

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

        def close(self):
            pass

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
            "name": "test-create-channel",
            "private": False,
            "mirror_channel_url": "http://my_remote_host",
            "mirror_mode": "proxy",
        },
    )
    assert response.status_code == 201

    response = client.get("/api/channels/test-create-channel")

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
            "name": "test-create-channel",
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

    dao.create_package(
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
        size=0,
    )
    yield version


@pytest.fixture
def owner(user, db):
    user = db.query(User).get(user.id)
    user.role = "owner"
    db.commit()
    yield user


DUMMY_PACKAGE = Path("./test-package-0.1-0.tar.bz2")
DUMMY_PACKAGE_V2 = Path("./test-package-0.2-0.tar.bz2")
OTHER_DUMMY_PACKAGE = Path("./other-package-0.1-0.tar.bz2")
OTHER_DUMMY_PACKAGE_V2 = Path("./other-package-0.2-0.tar.bz2")


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
                OTHER_DUMMY_PACKAGE,
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
                OTHER_DUMMY_PACKAGE_V2,
            ],
            "noarch",
            2,
            id="two-new-package-versions",
        ),
        # only one of the two is new
        pytest.param(
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"sha256": "OLD-SHA"}, "other-package-0.2-0.tar.bz2": {"sha256": "SHA-V2"}}}',  # noqa
                OTHER_DUMMY_PACKAGE_V2,
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
    mocker,
):
    pkgstore = config.get_package_store()
    rules = Rules("", {"user_id": str(uuid.UUID(bytes=user.id))}, db)

    class DummySession:
        def get(self, path, stream=False):
            return dummy_response()

        def close(self):
            pass

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
    ],
)
def test_synchronisation_no_checksums_in_db(
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
    mocker,
):

    package_info = '{"size": 5000, "subdirs":["noarch"]}'
    package_version.info = package_info
    db.commit()

    pkgstore = config.get_package_store()
    rules = Rules("", {"user_id": str(uuid.UUID(bytes=user.id))}, db)

    class DummySession:
        def get(self, path, stream=False):
            return dummy_response()

        def close(self):
            pass

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


@pytest.mark.skip(reason="disabled since _check_timestamp() is buggy")
@pytest.mark.parametrize(
    "repo_content,timestamp_mirror_sync,expected_timestamp,new_package",
    [
        # package modified but no server timestamp set
        (
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"time_modified": 100}}}',
                DUMMY_PACKAGE,
            ],
            0,
            100,
            True,
        ),
        # package modified with later timestamp
        (
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"time_modified": 1000}}}',  # noqa
                DUMMY_PACKAGE,
            ],
            100,
            1000,
            True,
        ),
        # package modified with earlier timestamp
        (
            [
                b'{"packages": {"test-package-0.1-0.tar.bz2": {"time_modified": 100}}}',
                DUMMY_PACKAGE,
            ],
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
            "name": "proxy-channel",
            "private": False,
            "mirror_channel_url": "http://host",
            "mirror_mode": "proxy",
        },
    )
    assert response.status_code == 201

    # download from remote server
    response = client.get("/get/proxy-channel/test_file.txt")

    assert response.status_code == 200
    assert response.content == b"Hello world!"
    assert dummy_repo == [("http://host/test_file.txt")]

    dummy_repo.pop()

    assert dummy_repo == []

    # serve from cache
    response = client.get("/get/proxy-channel/test_file.txt")

    assert response.status_code == 200
    assert response.content == b"Hello world!"

    assert dummy_repo == []

    # new file - download from remote
    response = client.get("/get/proxy-channel/test_file_2.txt")

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
            "name": "proxy-channel-2",
            "private": False,
            "mirror_channel_url": "http://host",
            "mirror_mode": "proxy",
        },
    )
    assert response.status_code == 201

    response = client.get("/get/proxy-channel-2/repodata.json")
    assert response.status_code == 200
    assert response.content == b"Hello world!"

    response = client.get("/get/proxy-channel-2/repodata.json")
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
        "/get/{}/missing/path/file.json".format(mirror_channel.name),
    )
    assert response.status_code == 404
    assert "file.json not found" in response.json()["detail"]


@pytest.mark.parametrize(
    "repo_content,expected_paths",
    [
        # linux-64 subdir without packages
        (
            [b'{"subdirs": ["linux-64"], "packages":{}}', b'{"packages": {}}'],
            ["channeldata.json", "linux-64/repodata_from_packages.json"],
        ),
        # empty repodata
        (
            [b'{"subdirs": ["linux-64"], "packages":{}}', b"{}"],
            ["channeldata.json", "linux-64/repodata_from_packages.json"],
        ),
        # no subodirs
        ([b'{"subdirs": [], "packages":{}}'], ["channeldata.json"]),
        # two arbitrary subdirs
        (
            [
                b'{"subdirs": ["some-arch-1", "some-arch-2"], "packages":{}}',
                b"{}",
                b"{}",
            ],
            [
                "channeldata.json",
                "some-arch-1/repodata_from_packages.json",
                "some-arch-2/repodata_from_packages.json",
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
            "name": "mirror-channel-" + str(uuid.uuid4())[:10],
            "private": False,
            "mirror_channel_url": host,
            "mirror_mode": "mirror",
        },
    )
    assert response.status_code == 201

    assert dummy_repo == [os.path.join(host, p) for p in expected_paths]


@pytest.mark.parametrize("user_role", ['maintainer'])
def test_add_mirror_without_sync(auth_client, dummy_repo):

    host = "http://mirror3_host"
    response = auth_client.post(
        "/api/channels",
        json={
            "name": "mirror-channel-" + str(uuid.uuid4())[:10],
            "private": False,
            "mirror_channel_url": host,
            "mirror_mode": "mirror",
            "metadata": {"actions": []},
        },
    )
    assert response.status_code == 201

    assert not dummy_repo


@pytest.fixture
def dummy_session_mock(app):

    dummy_session = MagicMock()

    def get_dummy_session():
        return dummy_session

    from quetz.main import get_remote_session

    app.dependency_overrides[get_remote_session] = get_dummy_session

    yield dummy_session

    app.dependency_overrides.pop(get_remote_session)


@pytest.mark.parametrize("user_role", ['maintainer'])
def test_add_and_register_mirror(auth_client, dummy_session_mock):

    host = "http://mirror3_host/get/my-channel"
    response = auth_client.post(
        "/api/channels",
        params={"register_mirror": "true"},
        json={
            "name": "mirror-channel",
            "private": False,
            "mirror_channel_url": host,
            "mirror_mode": "mirror",
            "metadata": {"actions": []},
        },
    )
    assert response.status_code == 201

    dummy_session_mock.post.assert_called_with(
        "http://mirror3_host/api/channels/my-channel/mirrors",
        json={
            "url": auth_client.base_url + '/get/mirror-channel',
            "api_endpoint": auth_client.base_url + '/api/channels/mirror-channel',
            "metrics_endpoint": auth_client.base_url
            + '/metrics/channels/mirror-channel',
        },
        headers={},
    )


empty_archive = b""


@pytest.mark.parametrize(
    "repo_content",
    [
        [
            b'{"subdirs": ["linux-64"], "packages":{}}',
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

    channel_name = "mirror-channel-" + str(uuid.uuid4())[:10]

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
        "http://mirror3_host/linux-64/repodata_from_packages.json",
        "http://mirror3_host/linux-64/my_package-0.1.tar.bz",
    ]

    # check if package was not added
    response = client.get(f"/api/channels/{channel_name}/packages")

    assert response.status_code == 200

    assert not response.json()


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
        (b'{"subdirs":["wonder-arch"], "packages":{}}', 200, ["wonder-arch"]),
    ],
)
def test_repo_without_channeldata(owner, client, dummy_repo, expected_archs):

    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post(
        "/api/channels",
        json={
            "name": "mirror-channel-" + str(uuid.uuid4())[:10],
            "private": False,
            "mirror_channel_url": "http://mirror3_host",
            "mirror_mode": "mirror",
        },
    )

    assert dummy_repo[0] == "http://mirror3_host/channeldata.json"
    for arch in expected_archs:
        assert (
            "http://mirror3_host/{}/repodata_from_packages.json".format(arch)
            in dummy_repo
        )
    if expected_archs is KNOWN_SUBDIRS:
        assert len(dummy_repo) == len(expected_archs) * 2 + 1
    else:
        assert len(dummy_repo) == len(expected_archs) * 1 + 1

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


@pytest.mark.parametrize(
    "package_list_type, expected_package",
    [("includelist", "nrnpython"), ("excludelist", "test-package")],
)
def test_packagelist_mirror_channel(
    owner, client, package_list_type, expected_package, db
):
    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post(
        "/api/channels",
        json={
            "name": "mirror-channel-btel",
            "private": False,
            "mirror_channel_url": "https://conda.anaconda.org/btel",
            "mirror_mode": "mirror",
            "metadata": {package_list_type: ["nrnpython"]},
        },
    )
    assert response.status_code == 201

    response = client.get("/api/channels/mirror-channel-btel/packages")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]['name'] == expected_package


def test_includelist_and_excludelist_mirror_channel(owner, client):
    response = client.get("/api/dummylogin/bartosz")
    assert response.status_code == 200

    response = client.post(
        "/api/channels",
        json={
            "name": "mirror-channel-btel",
            "private": False,
            "mirror_channel_url": "https://conda.anaconda.org/btel",
            "mirror_mode": "mirror",
            "metadata": {"includelist": ["nrnpython"], "excludelist": ["test-package"]},
        },
    )
    assert response.status_code == 422


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


channeldata_json = """
{
  "channeldata_version": 1,
  "packages": {
    "other-package": {
      "activate.d": false,
      "binary_prefix": false,
      "deactivate.d": false,
      "description": "descriptive description",
      "dev_url": null,
      "doc_source_url": null,
      "doc_url": null,
      "home": "https://palletsprojects.com/p/click/",
      "icon_hash": null,
      "icon_url": null,
      "identifiers": {},
      "keywords": {},
      "license": "BSD",
      "post_link": false,
      "pre_link": false,
      "pre_unlink": false,
      "run_exports": {},
      "source_git_url": null,
      "source_url": null,
      "subdirs": [
        "linux-64", "osx"
      ],
      "summary": "dummy package",
      "tags": {},
      "text_prefix": false,
      "timestamp": 1599839787,
      "version": "0.2"
    }
  },
  "subdirs": [
    "linux-64",
    "noarch"
  ]
}
"""

repodata_json = """
{
  "info": {
    "subdir": "linux-64"
  },
  "packages": {
    "other-package-0.2-0.tar.bz2": {
      "arch": "x86_64",
      "build": "0",
      "build_number": 0,
      "depends": [],
      "license": "BSD",
      "license_family": "BSD",
      "md5": "f5764fa8299aa117fce80be10d76724c",
      "name": "other-package",
      "platform": "linux",
      "sha256": "e46bd61cc2e9d269632314916c1187cc1c60a7f957a61dda38fe377824d28135",
      "size": 2706,
      "subdir": "linux-64",
      "timestamp": 1599839787253,
      "version": "0.2",
      "time_modified": 1608636247
    }
  },
  "packages.conda": {},
  "repodata_version": 1
}
"""


def test_create_packages_from_channeldata(dao, user, local_channel, db):
    channeldata = json.loads(channeldata_json)
    create_packages_from_channeldata(local_channel.name, user.id, channeldata, dao)

    package = db.query(Package).filter(Package.name == "other-package").one()

    assert package
    assert package.summary == "dummy package"


@pytest.fixture
def local_package(db, local_channel):
    pkg = Package(name="other-package", channel=local_channel)
    db.add(pkg)
    db.commit()
    # do not keep the instance because sqlalchemy won't allow creating duplicate
    return


@pytest.fixture
def dummy_user(db):

    new_user = User(id=uuid.uuid4().bytes, username="dummyuser", role="owner")
    db.add(new_user)
    db.commit()

    yield new_user

    db.delete(new_user)
    db.commit()


@pytest.mark.parametrize("auto_rollback", [False])
def test_create_packages_from_channeldata_update_existing(
    dao, dummy_user, local_channel, db, local_package
):
    # update exisiting package

    channeldata = json.loads(channeldata_json)

    create_packages_from_channeldata(
        local_channel.name, dummy_user.id, channeldata, dao
    )

    package = db.query(Package).filter(Package.name == "other-package").one()

    assert package

    assert package.description == "descriptive description"
    assert package.summary == "dummy package"
    assert package.url == "https://palletsprojects.com/p/click/"
    assert package.platforms == "linux-64:osx"
    assert json.loads(package.channeldata)["summary"] == "dummy package"

    # need to clean up manually due to auto_rollback=False option
    db.delete(package)
    db.commit()


def test_create_versions_from_repodata(dao, user, local_channel, db):

    pkg = Package(name="other-package", channel=local_channel)
    db.add(pkg)
    repodata = json.loads(repodata_json)
    create_versions_from_repodata(local_channel.name, user.id, repodata, dao)
    version = (
        db.query(PackageVersion)
        .filter(PackageVersion.package_name == "other-package")
        .one()
    )

    assert version


@pytest.fixture
def dummy_package_file(config):

    filepath = OTHER_DUMMY_PACKAGE_V2
    fid = open(filepath, 'rb')

    class DummyRemoteFile:

        filename = filepath.name
        content_type = "application/archive"
        file = fid

    yield DummyRemoteFile()

    fid.close()


@pytest.fixture
def rules(user, db):

    rules = Rules("", {"user_id": str(uuid.UUID(bytes=user.id))}, db)

    return rules


@pytest.mark.parametrize("user_role", ["owner"])
def test_handle_repodata_package(
    dao, user, local_channel, dummy_package_file, rules, config, db
):
    pkg = Package(name="other-package", channel=local_channel)
    db.add(pkg)

    repodata = json.loads(repodata_json)
    package_name, package_data = list(repodata["packages"].items())[0]
    pkgstore = config.get_package_store()

    files_metadata = [(dummy_package_file, package_name, package_data)]

    handle_repodata_package(
        local_channel.name, files_metadata, dao, rules, False, pkgstore, config
    )
    version = (
        db.query(PackageVersion)
        .filter(PackageVersion.package_name == "other-package")
        .one()
    )

    assert version

    pkgstore.serve_path(local_channel.name, f"linux-64/{package_name}")


@pytest.fixture
def plugin(app):
    from quetz.main import pm

    class Plugin:
        about = None

        @hookimpl
        def post_add_package_version(
            version,
            condainfo: CondaInfo,
        ):
            Plugin.about = condainfo.about

    plugin = Plugin()
    pm.register(plugin)
    yield plugin
    pm.unregister(plugin)


@pytest.mark.parametrize("user_role", ["owner"])
def test_handle_repodata_package_with_plugin(
    dao, local_channel, dummy_package_file, rules, config, db, plugin, user
):
    pkg = Package(name="other-package", channel=local_channel)
    db.add(pkg)

    repodata = json.loads(repodata_json)
    package_name, package_data = list(repodata["packages"].items())[0]
    pkgstore = config.get_package_store()

    files_metadata = [(dummy_package_file, package_name, package_data)]

    handle_repodata_package(
        local_channel.name, files_metadata, dao, rules, False, pkgstore, config
    )

    assert plugin.about['conda_version'] == '4.8.4'
