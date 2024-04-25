import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from libmambapy import bindings as libmamba_api


def offline_keys():
    return dict(
        root=libmamba_api.generate_ed25519_keypair(),
        key_mgr=libmamba_api.generate_ed25519_keypair(),
    )


def root_role_file(test_data_dir, offline_keys):
    filename = "root.json"
    filepath = Path(test_data_dir) / filename

    timestamp = datetime.now(timezone.utc)
    # avoid failing test due to expired role
    expiration = timestamp + timedelta(days=365)

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
        json.dump(json_role, f, indent=2)

    return filepath


def key_mgr_role_file(test_data_dir, offline_keys, signing_key):
    filename = "key_mgr.json"
    filepath = Path(test_data_dir) / filename

    timestamp = datetime.now(timezone.utc)
    # avoid failing test due to expired role
    expiration = timestamp + timedelta(days=365)

    json_role = {
        "signatures": {},
        "signed": {
            "delegations": {
                "pkg_mgr": {
                    "pubkeys": [signing_key],
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
        json.dump(json_role, f, indent=2)

    return filepath


def pkg_mgr_role_file(test_data_dir, private_key, public_key):
    filename = "pkg_mgr.json"
    filepath = Path(test_data_dir) / filename

    timestamp = datetime.now(timezone.utc)
    # avoid failing test due to expired role
    expiration = timestamp + timedelta(days=365)

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
        json.dumps(json_role["signed"], indent=2), private_key
    )
    json_role["signatures"][public_key] = {"signature": signature}

    with open(filepath, "w") as f:
        json.dump(json_role, f, indent=2)

    return filepath


if __name__ == "__main__":
    keys = offline_keys()
    test_data_dir = os.path.dirname(os.path.abspath(__file__))

    root_file = root_role_file(test_data_dir, keys)

    s = requests.Session()

    response = s.get("http://127.0.0.1:8000/api/content-trust/new-key?secret=true")
    public_key = response.json()["keyval"]
    private_key = response.json()["secret"]

    key_mgr_file = key_mgr_role_file(test_data_dir, keys, public_key)
    pkg_mgr_file = pkg_mgr_role_file(test_data_dir, private_key, public_key)

    # Login with channel0 owner
    response = s.get("http://127.0.0.1:8000/api/dummylogin/alice")
    assert response.status_code == 200

    # Create and get an API key
    api_key_request = {
        "description": "test-token",
        "roles": [{"role": "owner", "channel": "channel0"}],
    }

    response = s.post(
        "http://127.0.0.1:8000/api/api-keys", data=json.dumps(api_key_request)
    )
    assert response.status_code == 201

    response = s.get("http://127.0.0.1:8000/api/api-keys")
    assert response.status_code == 200
    api_key = response.json()[0]["key"]

    # Upload a 'root' role
    response = s.post(
        "http://127.0.0.1:8000/api/content-trust/channel0/roles?type=root",
        files={"file": (root_file.name, open(root_file, "rb"))},
    )
    assert response.status_code == 201
    print("'root' role file uploaded")

    # Upload a 'key_mgr' role
    response = s.post(
        "http://127.0.0.1:8000/api/content-trust/channel0/roles?type=key_mgr",
        files={"file": (key_mgr_file.name, open(key_mgr_file, "rb"))},
    )
    assert response.status_code == 201
    print("'key_mgr' (targets) role file uploaded")

    # Upload a 'pkg_mgr' role
    response = s.post(
        "http://127.0.0.1:8000/api/content-trust/channel0/roles?type=pkg_mgr",
        files={"file": (pkg_mgr_file.name, open(pkg_mgr_file, "rb"))},
    )
    assert response.status_code == 201
    print("'pkg_mgr' (targets delegation) role file uploaded")

    # Upload a test package to the server
    test_tarball = Path.cwd() / "quetz/tests/data/test-package-0.1-0.tar.bz2"
    push_package_request = {
        "name": "test-package",
        "platforms": ["linux-64"],
    }
    response = s.post(
        "http://127.0.0.1:8000/api/channels/channel0/files/",
        headers={"X-API-Key": f"{api_key}"},
        files=[("files", open(test_tarball, "rb"))],
    )
    assert response.status_code == 201
    print("'test-package' package uploaded")

    root_prefix = Path(os.environ["MAMBA_ROOT_PREFIX"])
    assert root_prefix

    channel_initial_trusted_root_role = root_prefix / "etc/trusted-repos/0f0a1dde"
    if not channel_initial_trusted_root_role.exists():
        os.makedirs(channel_initial_trusted_root_role)

    shutil.copy(
        Path.cwd() / "test_quetz/channels/channel0/root.json",
        root_prefix / "etc/trusted-repos/0f0a1dde/root.json",
    )
    print("Initial trusted root copied")

    existing_cache = root_prefix / "pkgs/cache/0f0a1dde"
    if existing_cache.exists():
        shutil.rmtree(existing_cache)
        print("cache cleaned")
