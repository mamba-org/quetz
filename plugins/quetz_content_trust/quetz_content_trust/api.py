import json
import os
from tempfile import SpooledTemporaryFile
from typing import Any, Callable, Dict, Iterable, Union

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from libmambapy import bindings as libmamba_api

from quetz import authorization
from quetz.config import Config
from quetz.database import get_db_manager
from quetz.deps import get_rules

from . import db_models

router = APIRouter(tags=["content-trust"])


def assert_role(signable: Dict[str, Any], builder: Callable):
    try:
        return builder(signable)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role definition"
        )


def assert_key_exists(key: str, db):
    query = db.query(db_models.RepodataSigningKey).filter(
        db_models.RepodataSigningKey.public_key == key,
    )
    if not query:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Key not found"
        )


def assert_keys_exist(keys: Iterable[str], db):
    for k in keys:
        assert_key_exists(k, db)


def post_role_file(file: Union[str, bytes], channel_name: str, builder: Callable):
    if type(file.file) is SpooledTemporaryFile and not hasattr(file, "seekable"):
        file.file.seekable = file.file._file.seekable

    file.file.seek(0, os.SEEK_END)
    file.file.seek(0)

    role = None
    with file.file as f:
        role = assert_role(json.load(f), builder)
        file.file.seek(0)
        Config().get_package_store().add_file(f.read(), channel_name, file.filename)

    return role


def role_builder(
    channel: str, role: str, delegation: db_models.RoleDelegation
) -> Callable:
    def root_builder(json_dict: Dict[str, Any]):
        return libmamba_api.RootImpl(json.dumps(json_dict))

    def key_mgr_builder(json_dict: Dict[str, Any]):
        keys = [k.public_key for k in delegation.keys]
        threshold = delegation.threshold

        spec = libmamba_api.SpecImpl()
        full_keys = libmamba_api.RoleFullKeys(
            keys={k: libmamba_api.Key.from_ed25519(k) for k in keys},
            threshold=threshold,
        )
        return libmamba_api.KeyMgr(json.dumps(json_dict), full_keys, spec)

    def pkg_mgr_builder(json_dict: Dict[str, Any]):
        keys = [k.public_key for k in delegation.keys]
        threshold = delegation.threshold

        spec = libmamba_api.SpecImpl()
        full_keys = libmamba_api.RoleFullKeys(
            keys={k: libmamba_api.Key.from_ed25519(k) for k in keys},
            threshold=threshold,
        )
        return libmamba_api.PkgMgr(json.dumps(json_dict), full_keys, spec)

    def wrong_role(_: Dict[str, Any]):
        raise RuntimeError()

    builder = dict(root=root_builder, key_mgr=key_mgr_builder, pkg_mgr=pkg_mgr_builder)

    return builder.get(role, wrong_role)


@router.post("/api/content-trust/{channel}/roles", status_code=201, tags=["files"])
def post_role(
    channel: str,
    type: str,
    file: UploadFile = File(...),
    force: bool = False,
    auth: authorization.Rules = Depends(get_rules),
):
    auth.assert_channel_roles(channel, ["owner"])

    with get_db_manager() as db:
        existing_role_count = (
            db.query(db_models.ContentTrustRole)
            .filter(
                db_models.ContentTrustRole.channel == channel,
                db_models.ContentTrustRole.type == type,
            )
            .count()
        )
        if not force and existing_role_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Content trust role '{type}' already exists "
                f"for channel '{channel}'",
            )

        def get_self_delegation(nullable: bool = False):
            query = (
                db.query(db_models.RoleDelegation)
                .filter(
                    db_models.RoleDelegation.type == type,
                    db_models.RoleDelegation.channel == channel,
                )
                .one_or_none()
            )

            if not query and not nullable:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"'{type}' keys not yet delegated",
                )
            return query

        self_delegation = get_self_delegation(nullable=type == "root")

        ct_role = post_role_file(
            file, channel, role_builder(channel, type, self_delegation)
        )

        db_role = db_models.ContentTrustRole(
            type=ct_role.type,
            channel=channel,
            version=ct_role.version,
            timestamp=ct_role.timestamp,
            expiration=ct_role.expires,
        )

        # add delegations
        for role_type, role_keys in ct_role.all_keys().items():
            keys = [
                db.merge(db_models.SigningKey(public_key=key_id))
                for key_id in role_keys.keys
            ]

            delegated_db_role = db_models.RoleDelegation(
                type=role_type,
                channel=channel,
                threshold=role_keys.threshold,
                keys=keys,
            )

            db_role.delegations.append(delegated_db_role)

        # set self_delegation if the role is 'root'
        if type == "root":
            # Error handling (missing 'root' delegation, etc.) is done by
            # mamba API when loading the root role from file
            self_delegation = [r for r in db_role.delegations if r.type == "root"][0]

        if not self_delegation:
            raise RuntimeError("self_delegation must not be None")

        # db_role.delegation = self_delegation
        self_delegation.consumers.append(db_role)

        db.add(db_role)

        db.commit()


@router.get("/api/content-trust/{channel}/roles")
def get_role(
    channel: str,
    type: str = None,
    auth: authorization.Rules = Depends(get_rules),
):
    auth.assert_channel_roles(channel, ["owner", "maintainer", "member"])

    with get_db_manager() as db:
        query = (
            db.query(db_models.ContentTrustRole)
            .filter(db_models.ContentTrustRole.channel == channel)
            .all()
        )

    return {q.delegation.keys for q in query}


@router.get("/api/content-trust/new-key")
def get_new_key(secret: bool = False):
    public_key, private_key = libmamba_api.generate_ed25519_keypair()
    key = db_models.SigningKey(
        public_key=public_key,
        private_key=private_key,
    )

    mamba_key = libmamba_api.Key.from_ed25519(key.public_key)
    private_key = key.private_key

    with get_db_manager() as db:
        db.add(key)
        db.commit()

    res = json.loads(mamba_key.json_str)
    if secret:
        res["secret"] = private_key

    return res
