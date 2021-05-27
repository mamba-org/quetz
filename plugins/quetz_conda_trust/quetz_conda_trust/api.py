import os

from fastapi import APIRouter, UploadFile, File, Depends

from quetz import authorization
from quetz.deps import get_rules
from quetz.config import Config

from tempfile import SpooledTemporaryFile

router = APIRouter()
config = Config()

pkgstore = config.get_package_store()

def post_file(file):
    if type(file.file) is SpooledTemporaryFile and not hasattr(file, "seekable"):
        file.file.seekable = file.file._file.seekable

    file.file.seek(0, os.SEEK_END)
    file.file.seek(0)

    # channel_name is passed as "" (empty string)
    # since we want to upload the file in a host-wide manner i.e. independent of individual channels
    # this hack only works for LocalStore since Azure and S3 necessarily require the creation of
    # `containers` and `buckets` (mapped to individual channels) before we can upload a file there.
    pkgstore.add_file(file.file.read(), "", file.filename)


@router.post("/api/conda-trust/upload-root", status_code=201, tags=["files"])
def post_root_json_to_channel(
    root_json_file: UploadFile = File(...),
    auth: authorization.Rules = Depends(get_rules),
):
    auth.assert_server_roles(["owner", "maintainer"])
    post_file(root_json_file)


@router.post("/api/conda-trust/upload-key-mgr", status_code=201, tags=["files"])
def post_root_json_to_channel(
    key_mgr_file: UploadFile = File(...),
    auth: authorization.Rules = Depends(get_rules),
):
    auth.assert_server_roles(["owner", "maintainer"])
    post_file(key_mgr_file)
