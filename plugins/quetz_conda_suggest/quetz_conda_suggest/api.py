import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm.session import Session

from quetz.config import Config
from quetz.deps import get_db

config = Config()
pkgstore = config.get_package_store()

router = APIRouter()


@router.get("/api/channels/{channel_name}/{subdir}/conda-suggest")
def get_conda_suggest(channel_name, subdir, db: Session = Depends(get_db)):
    map_filename = f"{channel_name}.{subdir}.map"
    map_filepath = pkgstore.url(channel_name, f"{subdir}/{map_filename}")
    try:
        if pkgstore.support_redirect:
            return RedirectResponse(map_filepath)
        elif os.path.isfile(map_filepath):
            return FileResponse(
                map_filepath,
                media_type="application/octet-stream",
                filename=map_filename,
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"conda-suggest map file for {channel_name}.{subdir} not found",
        )
