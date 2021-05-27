import os

from fastapi import APIRouter, UploadFile, File, Depends

from quetz import authorization, db_models
from quetz.deps import get_rules, ChannelChecker
from quetz.config import Config

from tempfile import SpooledTemporaryFile

router = APIRouter()
config = Config()

pkgstore = config.get_package_store()

@router.post("/api/channels/{channel_name}/conda-trust/files/root", status_code=201, tags=["files"])
def post_root_json_to_channel(
    channel_name,
    root_json_file: UploadFile = File(...),
    channel: db_models.Channel = Depends(
        ChannelChecker(allow_proxy=False, allow_mirror=False)
    ),
    auth: authorization.Rules = Depends(get_rules),
):
    user_id = auth.assert_user()
    auth.assert_upload_file(channel.name, root_json_file.filename)

    if type(root_json_file.file) is SpooledTemporaryFile and not hasattr(root_json_file, "seekable"):
        root_json_file.file.seekable = root_json_file.file._file.seekable

    root_json_file.file.seek(0, os.SEEK_END)
    root_json_file.file.seek(0)

    pkgstore.add_file(root_json_file.file.read(), "", root_json_file.filename)
    
