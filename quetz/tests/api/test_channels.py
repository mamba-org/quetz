import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import ANY

import pytest

from quetz import db_models
from quetz.authorization import (
    MAINTAINER,
    MEMBER,
    OWNER,
    SERVER_MAINTAINER,
    SERVER_MEMBER,
    SERVER_OWNER,
)
from quetz.condainfo import CondaInfo
from quetz.config import Config
from quetz.jobs.models import Job
from quetz.jobs.runner import Supervisor
from quetz.testing.mockups import MockWorker


@pytest.fixture
def maintainer(user, db):
    user.role = "maintainer"
    db.commit()


@pytest.mark.parametrize(
    "user_role,expected_status",
    [("owner", 201), ("maintainer", 201), ("member", 201), (None, 403)],
)
def test_create_normal_channel_permissions(auth_client, expected_status):

    response = auth_client.post(
        "/api/channels",
        json={
            "name": "test-create-channel",
            "private": False,
        },
    )
    assert response.status_code == expected_status


@pytest.mark.parametrize("channel_role", ["owner", "maintainer", "member"])
@pytest.mark.parametrize("user_role", ["owner", "maintainer", "member", None])
def test_delete_channel_permissions(
    db, auth_client, public_channel, user_role, channel_role
):

    response = auth_client.delete(f"/api/channels/{public_channel.name}")

    channel = (
        db.query(db_models.Channel)
        .filter(db_models.Channel.name == public_channel.name)
        .one_or_none()
    )

    if user_role in ["owner", "maintainer"] or channel_role in ["owner", "maintainer"]:
        assert response.status_code == 200
        assert channel is None
    else:
        assert response.status_code == 403
        assert channel is not None


@pytest.mark.parametrize("user_role", ["owner"])
def test_delete_channel_with_packages(
    db, auth_client, private_channel, private_package_version, config: Config
):

    pkg_store = config.get_package_store()
    pkg_store.add_file("test-file", private_channel.name, "test_file.txt")
    pkg_store.add_file("second", private_channel.name, "subdir/second_file.txt")

    response = auth_client.delete(f"/api/channels/{private_channel.name}")

    channel = (
        db.query(db_models.Channel)
        .filter(db_models.Channel.name == private_channel.name)
        .one_or_none()
    )

    version = (
        db.query(db_models.PackageVersion)
        .filter_by(package_name=private_package_version.package_name)
        .one_or_none()
    )
    package = (
        db.query(db_models.Package)
        .filter_by(name=private_package_version.package_name)
        .one_or_none()
    )

    files = pkg_store.list_files(private_channel.name)

    assert response.status_code == 200
    assert channel is None
    assert version is None
    assert package is None
    assert not files


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/channels/{channel_name}",
        "/api/channels/{channel_name}/packages",
        "/api/channels/{channel_name}/packages/{package_name}",
        "/api/channels/{channel_name}/packages/{package_name}/versions",
    ],
)
@pytest.mark.parametrize(
    "user_role,expected_status",
    [("owner", 200), ("maintainer", 200), ("member", 403), (None, 403)],
)
def test_permissions_channel_endpoints(
    auth_client,
    private_channel,
    expected_status,
    endpoint,
    private_package,
    private_package_version,
):

    response = auth_client.get(
        endpoint.format(
            channel_name=private_channel.name, package_name=private_package.name
        )
    )
    assert response.status_code == expected_status


@pytest.fixture
def sync_supervisor(db, dao, config):
    "supervisor with synchronous test worker"
    manager = MockWorker(config, db, dao)
    supervisor = Supervisor(db, manager)
    return supervisor


@pytest.mark.parametrize(
    "action", ['reindex', 'generate_indexes', 'synchronize_metrics']
)
@pytest.mark.parametrize(
    "channel_role,expected_code",
    [("owner", 200), ("maintainer", 200), ("member", 403), (None, 403)],
)
def test_channel_action_reindex(
    auth_client,
    public_channel,
    expected_code,
    action,
    user,
    remove_jobs,
    sync_supervisor,
):

    response = auth_client.put(
        f"/api/channels/{public_channel.name}/actions", json={"action": action}
    )

    assert response.status_code == expected_code
    if expected_code == 200:
        job_data = response.json()
        assert job_data == {
            "created": ANY,
            "id": ANY,
            "items_spec": None,
            "manifest": action,
            "owner_id": str(uuid.UUID(bytes=user.id)),
            "status": "pending",
            "repeat_every_seconds": None,
            "start_at": None,
        }
        job_id = job_data['id']
    else:
        return

    response = auth_client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    job_data = response.json()
    assert job_data == {
        "created": ANY,
        "id": job_id,
        "items_spec": None,
        "manifest": action,
        "owner_id": str(uuid.UUID(bytes=user.id)),
        "status": "pending",
        "repeat_every_seconds": None,
        "start_at": None,
    }

    sync_supervisor.run_jobs()

    response = auth_client.get(
        f"/api/jobs/{job_id}/tasks?"
        "status=created&status=running&status=pending&status=success"
    )

    assert response.status_code == 200
    all_tasks = response.json()['result']

    assert all_tasks == [
        {
            "job_id": job_id,
            'created': ANY,
            'id': ANY,
            'package_version': {},
            'status': 'created',
        }
    ]


@pytest.mark.parametrize("wait_seconds", [None, -5, 5, 0])
def test_create_delayed_action(
    auth_client,
    public_channel,
    user,
    remove_jobs,
    wait_seconds,
    sync_supervisor,
):

    action = "reindex"
    now = datetime.utcnow()
    if wait_seconds is None:
        start_at = None
    else:
        delta = timedelta(seconds=wait_seconds)
        start_at = (now + delta).isoformat()

    response = auth_client.put(
        f"/api/channels/{public_channel.name}/actions",
        json={"action": action, "start_at": start_at},
    )

    assert response.status_code == 200
    job_data = response.json()
    job_id = job_data['id']

    sync_supervisor.run_once()

    response = auth_client.get(
        f"/api/jobs/{job_id}/tasks?"
        "status=created&status=running&status=pending&status=success"
    )

    assert response.status_code == 200
    all_tasks = response.json()['result']

    if wait_seconds is not None and wait_seconds > 0:
        assert not all_tasks
    else:
        assert len(all_tasks) == 1


@pytest.mark.parametrize(
    "channel_role,expected_code",
    [("owner", 200), ("maintainer", 200), ("member", 403), (None, 403)],
)
def test_get_channel_members(auth_client, public_channel, expected_code):

    response = auth_client.get(f"/api/channels/{public_channel.name}/members")

    assert response.status_code == expected_code


@pytest.fixture
def remove_package_versions(db):
    yield
    db.query(db_models.PackageVersion).delete()


@pytest.fixture
def remove_jobs(db):
    yield
    db.query(Job).delete()


def test_channel_names_are_case_insensitive(
    auth_client, maintainer, remove_package_versions
):

    channel_name = "MyChanneL"

    response = auth_client.post(
        "/api/channels", json={"name": channel_name, "private": False}
    )

    assert response.status_code == 201

    response = auth_client.get(f"/api/channels/{channel_name}")

    assert response.status_code == 200
    assert response.json()["name"] == channel_name

    response = auth_client.get(f"/api/channels/{channel_name.lower()}")

    assert response.status_code == 200
    assert response.json()["name"] == channel_name

    response = auth_client.get(f"/api/channels/{channel_name.lower()}/packages")

    assert response.status_code == 200

    assert response.json() == []
    package_filename = "test-package-0.1-0.tar.bz2"
    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = auth_client.post(f"/api/channels/{channel_name}/files/", files=files)

    response = auth_client.get(f"/api/channels/{channel_name.lower()}/packages")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = auth_client.get(f"/api/channels/{channel_name}/packages")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "test-package"

    response = auth_client.get(
        f"/api/channels/{channel_name}/packages/test-package/versions"
    )
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = auth_client.get(
        f"/api/channels/{channel_name.lower()}/packages/test-package/versions"
    )
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = auth_client.get(f"/get/{channel_name.lower()}/linux-64/repodata.json")
    assert response.status_code == 200
    assert package_filename in response.json()["packages"]

    response = auth_client.get(f"/get/{channel_name.lower()}")
    assert response.status_code == 200

    response = auth_client.get(f"/get/{channel_name}")
    assert response.status_code == 200

    response = auth_client.get(f"/get/{channel_name}/linux-64/repodata.json")
    assert response.status_code == 200
    assert package_filename in response.json()["packages"]

    response = auth_client.get(
        f"/get/{channel_name.lower()}/linux-64/{package_filename}"
    )
    assert response.status_code == 200

    response = auth_client.get(f"/get/{channel_name}/linux-64/{package_filename}")
    assert response.status_code == 200


def test_unique_channel_names_are_case_insensitive(auth_client, maintainer):

    channel_name = "MyChanneL"

    response = auth_client.post(
        "/api/channels", json={"name": channel_name, "private": False}
    )

    assert response.status_code == 201

    response = auth_client.post(
        "/api/channels", json={"name": channel_name.lower(), "private": False}
    )

    assert response.status_code == 409
    assert f"{channel_name.lower()} exists" in response.json()["detail"]

    response = auth_client.post(
        "/api/channels", json={"name": channel_name.upper(), "private": False}
    )

    assert response.status_code == 409
    assert f"{channel_name.upper()} exists" in response.json()["detail"]


def test_unicode_channel_names(auth_client, maintainer):

    channel_name = "검은맘바"

    response = auth_client.post(
        "/api/channels", json={"name": channel_name, "private": False}
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "only ASCII characters should be used in channel name"
    )

    response = auth_client.get("/api/channels")

    assert response.status_code == 200
    assert len(response.json()) == 0

    response = auth_client.get(f"/api/channels/{channel_name}")

    assert response.status_code == 404


def test_accents_make_unique_channel_names(auth_client, maintainer):

    channel_names = ["żmija", "zmija", "grün", "grun"]

    for i, name in enumerate(channel_names):
        response = auth_client.post(
            "/api/channels", json={"name": name, "private": False}
        )
        if (i % 2) == 0:
            assert response.status_code == 422
            assert (
                response.json()["detail"]
                == "only ASCII characters should be used in channel name"
            )
        else:
            assert response.status_code == 201

    response = auth_client.get("/api/channels")

    assert response.status_code == 200

    assert len(response.json()) == 2


def test_upload_package_version_to_channel(
    auth_client,
    public_channel,
    maintainer,
    db,
    config,
    remove_package_versions,
):
    pkgstore = config.get_package_store()

    assert public_channel.size == 0

    package_filename = "test-package-0.1-0.tar.bz2"
    with open(package_filename, "rb") as fid:
        files = {"files": (package_filename, fid)}
        response = auth_client.post(
            f"/api/channels/{public_channel.name}/files/",
            files=files,
        )

    with open(package_filename, "rb") as fid:
        condainfo = CondaInfo(fid, package_filename)
        condainfo._parse_conda()

    assert response.status_code == 201
    db.refresh(public_channel)
    assert public_channel.size == condainfo.info["size"]
    assert pkgstore.serve_path(
        public_channel.name, str(Path(condainfo.info["subdir"]) / package_filename)
    )


@pytest.mark.parametrize("user_role", ["maintainer"])
@pytest.mark.parametrize(
    "config_extra,expected_size_limit",
    [("", None), ("[quotas]\nchannel_quota=100\n", 100), ("[quotas]\n", None)],
)
def test_create_channel_default_quotas(auth_client, expected_size_limit, db, config):

    name = "test-create-channel-with-quotas"
    response = auth_client.post(
        "/api/channels",
        json={
            "name": name,
            "private": False,
        },
    )

    assert response.status_code == 201

    channel = db.query(db_models.Channel).filter(db_models.Channel.name == name).one()

    if expected_size_limit is None:
        assert channel.size_limit is None
    else:
        assert channel.size_limit == expected_size_limit


@pytest.mark.parametrize("user_role", [SERVER_MAINTAINER, SERVER_OWNER, SERVER_MEMBER])
@pytest.mark.parametrize(
    "config_extra",
    [
        pytest.param("", id="no-config"),
        pytest.param("[quotas]\nchannel_quota=10\n", id="with-config"),
    ],
)
def test_create_channel_with_limits(auth_client, db, user_role):
    name = "test-create-channel-with-quotas"
    response = auth_client.post(
        "/api/channels",
        json={"name": name, "private": False, "size_limit": 101},
    )

    channel = (
        db.query(db_models.Channel).filter(db_models.Channel.name == name).one_or_none()
    )
    if user_role in [SERVER_MAINTAINER, SERVER_OWNER]:
        assert response.status_code == 201
        assert channel.size_limit == 101
    else:
        assert response.status_code == 403
        assert channel is None
        assert "set channel size limit" in response.json()["detail"][0]


@pytest.mark.parametrize("user_role", [SERVER_MAINTAINER, SERVER_OWNER])
def test_set_channel_size_limit(auth_client, db, public_channel):

    assert public_channel.size_limit is None

    response = auth_client.patch(
        f"/api/channels/{public_channel.name}",
        json={"size_limit": 101},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["name"] == public_channel.name
    assert data["size_limit"] == 101

    db.refresh(public_channel)

    assert public_channel.size_limit == 101


@pytest.mark.parametrize("ttl", [None, 1200, 36000])
@pytest.mark.parametrize("user_role", [SERVER_OWNER])
def test_create_channel_ttl(auth_client, db, user_role, ttl):
    name = "test-create-channel-ttl"
    payload = {"name": name, "private": False}
    if ttl is not None:
        payload["ttl"] = ttl
    response = auth_client.post("/api/channels", json=payload)
    channel = (
        db.query(db_models.Channel).filter(db_models.Channel.name == name).one_or_none()
    )
    assert response.status_code == 201
    if ttl is None:
        expected_ttl = 36000
    else:
        expected_ttl = ttl
    assert channel.ttl == expected_ttl


@pytest.mark.parametrize("user_role", [SERVER_OWNER])
def test_update_channel_ttl(auth_client, db, public_channel):

    assert public_channel.ttl == 36000

    response = auth_client.patch(
        f"/api/channels/{public_channel.name}",
        json={"ttl": 1200},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["name"] == public_channel.name
    assert data["ttl"] == 1200

    db.refresh(public_channel)

    assert public_channel.ttl == 1200


@pytest.mark.parametrize("user_role", [SERVER_OWNER])
@pytest.mark.parametrize(
    "attr_dict",
    [
        {"name": "new-name"},
        {"mirror_channel_url": "http://test", "mirror_mode": "proxy"},
    ],
)
def test_update_channel_forbidden_attributes(
    auth_client,
    db,
    public_channel,
    attr_dict,
):

    response = auth_client.patch(
        f"/api/channels/{public_channel.name}",
        json=attr_dict,
    )

    assert response.status_code == 422
    assert "can not be changed" in response.json()["detail"]


@pytest.mark.parametrize("user_role", [SERVER_OWNER])
@pytest.mark.parametrize("name,value", [("private", True)])
def test_update_channel_attributes(auth_client, db, public_channel, name, value):

    response = auth_client.patch(
        f"/api/channels/{public_channel.name}",
        json={name: value},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["name"] == public_channel.name
    assert data[name] == value

    db.refresh(public_channel)

    assert getattr(public_channel, name) == value


@pytest.mark.parametrize(
    "user_role", [SERVER_OWNER, SERVER_MEMBER, SERVER_MAINTAINER, None]
)
@pytest.mark.parametrize("channel_role", [OWNER, MAINTAINER, MEMBER])
def test_update_channel_permissions(
    auth_client, db, public_channel, user_role, channel_role
):

    response = auth_client.patch(
        f"/api/channels/{public_channel.name}",
        json={"private": False},
    )

    if user_role in [SERVER_OWNER, SERVER_MAINTAINER]:
        assert response.status_code == 200
    elif channel_role in [OWNER, MAINTAINER]:
        assert response.status_code == 200
    else:
        assert response.status_code == 403


@pytest.fixture
def remote_session(app, request, public_channel, auth_client):

    mirror_url = f"{auth_client.base_url}/get/{public_channel.name}"

    from quetz.main import get_remote_session

    class dummy_response:
        status_code = 200

        def json(self):
            return {"mirror_channel_url": mirror_url}

    class dummy_session:
        def get(self, url):
            return dummy_response()

    app.dependency_overrides[get_remote_session] = dummy_session

    return dummy_session


def test_register_mirror(auth_client, public_channel, db, remote_session):

    mirror_url = "http://mirror_url/get/my-channel"

    response = auth_client.post(
        f"/api/channels/{public_channel.name}/mirrors", json={"url": mirror_url}
    )

    m = db.query(db_models.ChannelMirror).filter_by(url=mirror_url).one_or_none()

    assert response.status_code == 201
    assert m
    assert m.last_synchronised is None

    response = auth_client.get(f"/api/channels/{public_channel.name}/mirrors")

    assert response.status_code == 200

    assert response.json() == [
        {
            "url": mirror_url,
            "id": ANY,
            "api_endpoint": "http://mirror_url/api/channels/my-channel",
            "metrics_endpoint": "http://mirror_url/metrics/channels/my-channel",
        }
    ]

    mirror_id = response.json()[0]["id"]
    response = auth_client.delete(
        f"/api/channels/{public_channel.name}/mirrors/{mirror_id}"
    )

    assert response.status_code == 200

    response = auth_client.get(f"/api/channels/{public_channel.name}/mirrors")

    assert response.status_code == 200

    assert response.json() == []


def test_url_with_slash(auth_client, public_channel, db, remote_session):

    mirror_url = "http://mirror_url"

    response = auth_client.post(
        f"/api/channels/{public_channel.name}/mirrors/", json={"url": mirror_url}
    )

    assert response.status_code == 307


@pytest.mark.parametrize(
    "auth_user,owned_channels",
    [("bartosz", ["my-channel"]), ("other", ["private-channel"])],
)
@pytest.mark.parametrize("include_public", [1, 0])
@pytest.mark.parametrize("endpoint", ["channels", "paginated/channels"])
def test_list_channels(
    client,
    private_channel,
    public_channel,
    auth_user,
    include_public,
    owned_channels,
    endpoint,
):
    response = client.get(f"/api/dummylogin/{auth_user}")
    assert response.status_code == 200

    response = client.get(f"/api/{endpoint}?public={include_public}")
    assert response.status_code == 200
    results = response.json()

    try:
        results = results['result']
    except TypeError:
        # non-paginated response
        pass

    channel_names = {r["name"] for r in results}

    if include_public:
        expected_channels = {public_channel.name, *owned_channels}
    else:
        expected_channels = set(owned_channels)

    assert channel_names == expected_channels


@pytest.mark.parametrize("endpoint", ["/api/channels/{channel_name}", "/api/channels"])
def test_channel_package_members_count(
    auth_client, public_channel, db, private_channel, other_user, endpoint
):
    response = auth_client.get(endpoint.format(channel_name=public_channel.name))
    assert response.status_code == 200

    channel_data = response.json()
    if isinstance(channel_data, list):
        channel_data = channel_data[0]

    assert channel_data['members_count'] == 1
    assert channel_data['packages_count'] == 0

    package = db_models.Package(channel=public_channel, name="test-package")
    db.add(package)
    db.commit()

    response = auth_client.get(endpoint.format(channel_name=public_channel.name))
    channel_data = response.json()
    if isinstance(channel_data, list):
        channel_data = channel_data[0]

    assert channel_data['packages_count'] == 1
    assert channel_data['members_count'] == 1

    package = db_models.Package(
        channel=private_channel, name="test-package-different-channel"
    )
    db.add(package)
    db.commit()

    response = auth_client.get(endpoint.format(channel_name=public_channel.name))
    channel_data = response.json()
    if isinstance(channel_data, list):
        channel_data = channel_data[0]

    assert channel_data['packages_count'] == 1
    assert channel_data['members_count'] == 1

    channel_member = db_models.ChannelMember(
        channel=public_channel, user=other_user, role="member"
    )
    db.add(channel_member)
    db.commit()

    response = auth_client.get(endpoint.format(channel_name=public_channel.name))
    channel_data = response.json()
    if isinstance(channel_data, list):
        channel_data = channel_data[0]

    assert channel_data['packages_count'] == 1
    assert channel_data['members_count'] == 2
