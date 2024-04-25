import datetime
import json
import pathlib
import uuid

import pytest
from libmambapy import bindings as libmamba_api
from pytest import fixture
from quetz_content_trust import db_models

from quetz import rest_models
from quetz.db_models import User

pytest_plugins = "quetz.testing.fixtures"


@pytest.fixture
def expires_on_commit():
    return False


@pytest.fixture
def plugins():
    return ["quetz-content_trust"]


@fixture
def username():
    yield "foobar"


@fixture
def channel_role():
    yield "owner"


@fixture
def logged():
    yield True


@fixture
def user(client, db, username, logged):
    user = User(id=uuid.uuid4().bytes, username=username)
    db.add(user)
    db.commit()

    if logged:
        client.get(f"/api/dummylogin/{user.username}")

    yield user


@fixture
def channel(dao, db, user, channel_role):
    channel_data = rest_models.Channel(
        name="test-channel",
        private=False,
    )

    if channel_role:
        c = dao.create_channel(channel_data, user_id=user.id, role=channel_role)
    else:
        c = dao.create_channel(channel_data)

    yield c


@fixture
def signing_key(db, user, channel):
    public_key, private_key = libmamba_api.generate_ed25519_keypair()
    key = db_models.SigningKey(
        public_key=public_key,
        private_key=private_key,
    )

    db.add(key)
    db.commit()

    yield key


@fixture
def offline_keys():
    return dict(
        root=libmamba_api.generate_ed25519_keypair(),
        key_mgr=libmamba_api.generate_ed25519_keypair(),
    )


@fixture
def root_role_file(tmp_path, offline_keys):
    filename = "root.json"
    filepath = pathlib.Path(tmp_path) / filename

    timestamp = datetime.datetime.now(datetime.timezone.utc)
    # avoid failing test due to expired role
    expiration = timestamp + datetime.timedelta(days=365)

    json_role = {
        "signatures": {},
        "signed": {
            "delegations": {
                "key_mgr": {
                    "pubkeys": [offline_keys["key_mgr"][0]],
                    "threshold": 1,
                },
                "root": {
                    "pubkeys": [offline_keys["root"][0]],
                    "threshold": 1,
                },
            },
            "expiration": expiration.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "metadata_spec_version": "0.6.0",
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": "root",
            "version": 1,
        },
    }

    signature = libmamba_api.sign(
        json.dumps(json_role["signed"], indent=2), offline_keys["root"][1]
    )
    json_role["signatures"][offline_keys["root"][0]] = {"signature": signature}

    with open(filepath, "w") as f:
        json.dump(json_role, f)

    yield filepath


@fixture
def key_mgr_role_file(tmp_path, offline_keys, signing_key):
    filename = "key_mgr.json"
    filepath = pathlib.Path(tmp_path) / filename

    timestamp = datetime.datetime.now(datetime.timezone.utc)
    # avoid failing test due to expired role
    expiration = timestamp + datetime.timedelta(days=365)

    json_role = {
        "signatures": {},
        "signed": {
            "delegations": {
                "pkg_mgr": {
                    "pubkeys": [signing_key.public_key],
                    "threshold": 1,
                }
            },
            "expiration": expiration.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "metadata_spec_version": "0.6.0",
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": "key_mgr",
            "version": 1,
        },
    }

    signature = libmamba_api.sign(
        json.dumps(json_role["signed"], indent=2), offline_keys["key_mgr"][1]
    )
    json_role["signatures"][offline_keys["key_mgr"][0]] = {"signature": signature}

    with open(filepath, "w") as f:
        json.dump(json_role, f)

    yield filepath


@fixture
def pkg_mgr_role_file(tmp_path, offline_keys, signing_key):
    filename = "pkg_mgr.json"
    filepath = pathlib.Path(tmp_path) / filename

    timestamp = datetime.datetime.now(datetime.timezone.utc)
    # avoid failing test due to expired role
    expiration = timestamp + datetime.timedelta(days=365)

    json_role = {
        "signatures": {},
        "signed": {
            "delegations": {},
            "expiration": expiration.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "metadata_spec_version": "0.6.0",
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": "pkg_mgr",
            "version": 1,
        },
    }

    signature = libmamba_api.sign(
        json.dumps(json_role["signed"], indent=2), signing_key.private_key
    )
    json_role["signatures"][signing_key.public_key] = {"signature": signature}

    with open(filepath, "w") as f:
        json.dump(json_role, f)

    yield filepath


@fixture
def signed_package(
    client, channel, root_role_file, key_mgr_role_file, pkg_mgr_role_file
):
    client.post(
        f"/api/content-trust/{channel.name}/roles?type=root",
        files={"file": (root_role_file.name, open(root_role_file, "rb"))},
    )
    client.post(
        f"/api/content-trust/{channel.name}/roles?type=key_mgr",
        files={"file": (key_mgr_role_file.name, open(key_mgr_role_file, "rb"))},
    )
    client.post(
        f"/api/content-trust/{channel.name}/roles?type=pkg_mgr",
        files={"file": (pkg_mgr_role_file.name, open(pkg_mgr_role_file, "rb"))},
    )

    pkg_filename = "test-package-0.1-0.tar.bz2"
    url = f"/api/channels/{channel.name}/files/"
    files_to_upload = {"files": (pkg_filename, open(pkg_filename, "rb"))}
    client.post(url, files=files_to_upload)

    yield pkg_filename
