import os
import shutil
import tarfile
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from .repo_signer import RepoSigner

router = APIRouter()

@router.get("/api/channels/{channel_name}/{subdir}/conda-trust")
def get_conda_trust(channel_name, subdir):
    repodata_folderpath = os.path.join(
        os.getcwd(), "channels", channel_name, subdir
    )

    rs = RepoSigner(repodata_folderpath)

    signed_repodata = os.path.join(repodata_folderpath, "repodata_signed.json")

    if os.path.isfile(signed_repodata):
        return FileResponse(
            signed_repodata,
            media_type="application/octet-stream",
            filename=f"{channel_name}_{subdir}_repodata_signed.json",
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"signed repodata for {channel_name} and {subdir} not found",
        )
