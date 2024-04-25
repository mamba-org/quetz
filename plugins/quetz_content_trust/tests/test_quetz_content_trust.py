import json

import pytest
from quetz_content_trust import db_models


@pytest.fixture
def trust_roles():
    return ["root.json"]


@pytest.fixture
def package_files(pkgstore, channel, trust_roles):
    pkgstore.create_channel(channel.name)
    for filename in trust_roles:
        with open(filename, "rb") as fid:
            content = fid.read()
        pkgstore.add_file(content, channel.name, f"linux-64/{filename}")


@pytest.mark.parametrize(
    "logged,channel_role,expected_status",
    [
        (False, None, 401),
        (True, None, 403),
        (True, "member", 403),
        (True, "maintainer", 403),
        (True, "owner", 201),
    ],
)
def test_post_root_role_permissions(
    client, channel, root_role_file, logged, channel_role, expected_status
):
    """Check post of root role requires 'owner' channel permissions"""

    response = client.post(
        f"/api/content-trust/{channel.name}/roles?type=root",
        files={"file": (root_role_file.name, open(root_role_file, "rb"))},
    )
    assert response.status_code == expected_status


def test_post_root_role(client, channel, db, root_role_file, offline_keys):
    """Check database keys/delegations/roles after posting root role"""

    client.post(
        f"/api/content-trust/{channel.name}/roles?type=root",
        files={"file": (root_role_file.name, open(root_role_file, "rb"))},
    )

    # Check keys
    assert db.query(db_models.SigningKey).count() == 2

    root_key = (
        db.query(db_models.SigningKey)
        .join(db_models.RoleDelegation.keys)
        .filter(db_models.RoleDelegation.type == "root")
        .one()
    )
    assert root_key.public_key == offline_keys["root"][0]

    key_mgr_key = (
        db.query(db_models.SigningKey)
        .join(db_models.RoleDelegation.keys)
        .filter(db_models.RoleDelegation.type == "key_mgr")
        .one()
    )
    assert key_mgr_key.public_key == offline_keys["key_mgr"][0]

    # Check delegations
    assert db.query(db_models.RoleDelegation).count() == 2

    root_delegation = (
        db.query(db_models.RoleDelegation)
        .filter(db_models.RoleDelegation.type == "root")
        .one()
    )
    assert root_delegation.channel == channel.name
    assert len(root_delegation.keys) == 1
    assert len(root_delegation.consumers) == 1

    key_mgr_delegation = (
        db.query(db_models.RoleDelegation)
        .filter(db_models.RoleDelegation.type == "key_mgr")
        .one()
    )
    assert key_mgr_delegation.channel == channel.name
    assert len(key_mgr_delegation.keys) == 1
    assert len(key_mgr_delegation.consumers) == 0

    root_role = db.query(db_models.ContentTrustRole).one()
    assert root_delegation.issuer == root_role
    assert key_mgr_delegation.issuer == root_role

    # Check roles
    assert db.query(db_models.ContentTrustRole).count() == 1

    assert root_role.channel == channel.name
    assert len(root_role.delegations) == 2
    assert root_role.delegations[0] == key_mgr_delegation
    assert root_role.delegations[1] == root_delegation
    assert root_role.delegator == root_delegation


def test_delegation_cascade_deletion(client, channel, db, root_role_file):
    """Check cascade deletion"""

    client.post(
        f"/api/content-trust/{channel.name}/roles?type=root",
        files={"file": (root_role_file.name, open(root_role_file, "rb"))},
    )

    root_delegation = (
        db.query(db_models.RoleDelegation)
        .filter(db_models.RoleDelegation.type == "root")
        .one()
    )

    # Check cascade delete
    db.delete(root_delegation)
    assert db.query(db_models.RoleDelegation).count() == 0
    assert db.query(db_models.ContentTrustRole).count() == 0
    assert db.query(db_models.SigningKey).count() == 2


def test_overwrite_root_role(client, root_role_file, channel):
    """Check overwriting 'root' role is not permitted"""

    response = client.post(
        f"/api/content-trust/{channel.name}/roles?type=root",
        files={"file": (root_role_file.name, open(root_role_file, "rb"))},
    )
    assert response.status_code == 201

    response = client.post(
        f"/api/content-trust/{channel.name}/roles?type=root",
        files={"file": (root_role_file.name, open(root_role_file, "rb"))},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "logged,channel_role,expected_status",
    [
        (False, None, 401),
        (True, None, 403),
        (True, "member", 200),
        (True, "maintainer", 200),
        (True, "owner", 200),
    ],
)
def test_get_root_role(client, channel, logged, channel_role, expected_status):
    """Check get 'root' role requires 'member' channel permissions"""

    response = client.get(f"/api/content-trust/{channel.name}/roles")
    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "logged,channel_role,expected_status",
    [
        (False, None, 401),
        (True, None, 403),
        (True, "member", 403),
        (True, "maintainer", 403),
        (True, "owner", 201),
    ],
)
def test_post_key_mgr_role(
    client,
    channel,
    root_role_file,
    key_mgr_role_file,
    logged,
    channel_role,
    expected_status,
):
    """Check posting 'key_mgr' role requires 'owner' channel permissions"""

    response = client.post(
        f"/api/content-trust/{channel.name}/roles?type=root",
        files={"file": (root_role_file.name, open(root_role_file, "rb"))},
    )
    assert response.status_code == expected_status

    response = client.post(
        f"/api/content-trust/{channel.name}/roles?type=key_mgr",
        files={"file": (key_mgr_role_file.name, open(key_mgr_role_file, "rb"))},
    )
    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "logged,channel_role,expected_status",
    [
        (False, None, 401),
        (True, None, 403),
        (True, "member", 403),
        (True, "maintainer", 403),
        (True, "owner", 400),
    ],
)
def test_post_key_mgr_role_wo_delegation(
    client, channel, key_mgr_role_file, logged, channel_role, expected_status
):
    """Check posting 'key_mgr' role requires delegation from 'root' role"""

    response = client.post(
        f"/api/content-trust/{channel.name}/roles?type=key_mgr",
        files={"file": (key_mgr_role_file.name, open(key_mgr_role_file, "rb"))},
    )
    assert response.status_code == expected_status


def test_get_new_key(client):
    """Check get a new key pair"""

    response = client.get("/api/content-trust/new-key")

    assert response.status_code == 200
    key = response.json()

    assert "keytype" in key and key["keytype"] == "ed25519"
    assert "scheme" in key and key["scheme"] == "ed25519"
    assert "keyval" in key and len(key["keyval"]) == 64


@pytest.mark.parametrize(
    "logged,channel_role,expected_status",
    [
        (False, None, 401),
        (True, None, 403),
        (True, "member", 403),
        (True, "maintainer", 403),
        (True, "owner", 201),
    ],
)
def test_post_pkg_mgr_role(
    client,
    channel,
    root_role_file,
    key_mgr_role_file,
    pkg_mgr_role_file,
    logged,
    channel_role,
    expected_status,
):
    """Check posting 'pkg_mgr' role requires delegation from 'key_mgr' role"""

    response = client.post(
        f"/api/content-trust/{channel.name}/roles?type=root",
        files={"file": (root_role_file.name, open(root_role_file, "rb"))},
    )
    assert response.status_code == expected_status

    response = client.post(
        f"/api/content-trust/{channel.name}/roles?type=key_mgr",
        files={"file": (key_mgr_role_file.name, open(key_mgr_role_file, "rb"))},
    )
    assert response.status_code == expected_status

    response = client.post(
        f"/api/content-trust/{channel.name}/roles?type=pkg_mgr",
        files={"file": (pkg_mgr_role_file.name, open(pkg_mgr_role_file, "rb"))},
    )
    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "logged,channel_role,delegators_status,expected_status",
    [
        (False, None, 401, 401),
        (True, None, 403, 403),
        (True, "member", 403, 403),
        (True, "maintainer", 403, 403),
        (True, "owner", 201, 400),
    ],
)
def test_post_pkg_mgr_role_wo_delegation(
    client,
    channel,
    root_role_file,
    key_mgr_role_file,
    pkg_mgr_role_file,
    logged,
    channel_role,
    delegators_status,
    expected_status,
):
    """Check posting 'pkg_mgr' role requires delegation from 'key_mgr' role"""

    response = client.post(
        f"/api/content-trust/{channel.name}/roles?type=pkg_mgr",
        files={"file": (pkg_mgr_role_file.name, open(pkg_mgr_role_file, "rb"))},
    )
    assert response.status_code == expected_status

    response = client.post(
        f"/api/content-trust/{channel.name}/roles?type=root",
        files={"file": (root_role_file.name, open(root_role_file, "rb"))},
    )
    assert response.status_code == delegators_status

    response = client.post(
        f"/api/content-trust/{channel.name}/roles?type=pkg_mgr",
        files={"file": (pkg_mgr_role_file.name, open(pkg_mgr_role_file, "rb"))},
    )
    assert response.status_code == expected_status


def test_post_index_signed_repodata(config, channel, signed_package, signing_key):
    pkgstore = config.get_package_store()
    signed_repodata = json.load(
        pkgstore.serve_path(channel.name, "linux-64/repodata.json")
    )

    public_key = signing_key.public_key

    assert "signatures" in signed_repodata
    assert signed_package in signed_repodata["signatures"]
    assert public_key in signed_repodata["signatures"][signed_package]
    assert len(signed_repodata["signatures"][signed_package]) == 1
    assert "signature" in signed_repodata["signatures"][signed_package][public_key]
    assert (
        len(signed_repodata["signatures"][signed_package][public_key]["signature"])
        == 128
    )
