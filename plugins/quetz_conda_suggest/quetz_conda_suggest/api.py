import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm.session import Session

from quetz.deps import get_db

router = APIRouter()


@router.get("/api/channels/{channel_name}/{subdir}/conda-suggest")
def get_conda_suggest(channel_name, subdir, db: Session = Depends(get_db)):
    map_filename = "{0}.{1}.map".format(channel_name, subdir)
    map_filepath = os.path.join(
        os.getcwd(), "channels", channel_name, subdir, map_filename
    )

    if os.path.isfile(map_filepath):
        return FileResponse(
            map_filepath,
            media_type="application/octet-stream",
            filename=map_filename,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"conda-suggest map file for {channel_name}.{subdir} not found",
        )
