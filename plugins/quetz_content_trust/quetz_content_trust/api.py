import os
from contextlib import contextmanager
from tempfile import SpooledTemporaryFile

from fastapi import APIRouter, Depends, File, UploadFile

from quetz import authorization
from quetz.config import Config
from quetz.database import get_session
from quetz.deps import get_rules

from . import db_models
from .rest_models import SigningKey

router = APIRouter()
config = Config()

pkgstore = config.get_package_store()


@contextmanager
def get_db_manager():

    db = get_session(config.sqlalchemy_database_url)

    try:
        yield db
    finally:
        db.close()


def post_file(file, channel_name):
    if type(file.file) is SpooledTemporaryFile and not hasattr(file, "seekable"):
        file.file.seekable = file.file._file.seekable

    file.file.seek(0, os.SEEK_END)
    file.file.seek(0)

    pkgstore.add_file(file.file.read(), channel_name, file.filename)


@router.post("/api/content-trust/private-key")
def post_pkg_mgr_private_key(
    repodata_signing_key: SigningKey,
    auth: authorization.Rules = Depends(get_rules),
):
    user_id = auth.assert_user()
    channel_name = repodata_signing_key.channel
    private_key = repodata_signing_key.private_key

    auth.assert_channel_roles(channel_name, ["owner"])

    with get_db_manager() as db:
        pkg_mgr_key = db_models.RepodataSigningKey(
            private_key=private_key, user_id=user_id, channel_name=channel_name
        )
        db.add(pkg_mgr_key)
        db.commit()


@router.post("/api/content-trust/upload-root", status_code=201, tags=["files"])
def post_root_json_to_channel(
    channel_name: str,
    root_json_file: UploadFile = File(...),
    auth: authorization.Rules = Depends(get_rules),
):
    auth.assert_channel_roles(channel_name, ["owner"])
    post_file(root_json_file, channel_name)


@router.post("/api/content-trust/upload-key-mgr", status_code=201, tags=["files"])
def post_key_mgr_to_channel(
    channel_name: str,
    key_mgr_file: UploadFile = File(...),
    auth: authorization.Rules = Depends(get_rules),
):
    auth.assert_channel_roles(channel_name, ["owner"])
    post_file(key_mgr_file, channel_name)
