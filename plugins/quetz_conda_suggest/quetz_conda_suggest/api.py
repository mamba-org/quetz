import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm.session import Session

from quetz.db_models import PackageVersion
from quetz.deps import get_db

router = APIRouter()


@router.get("/api/channels/{channel_name}/conda-suggest")
def get_conda_suggest(channel_name, db: Session = Depends(get_db)):
    all_packages = (
        db.query(PackageVersion)
        .filter(PackageVersion.channel_name == channel_name)
        .all()
    )

    channel_suggest_map = {}
    error = False
    for each_package in all_packages:
        if not each_package.files:
            error = True
        else:
            files_data = json.loads(each_package.files.data)
            for (k, v) in files_data.items():
                channel_suggest_map[k] = v

    if error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="files for all packages not found",
        )

    with open("{0}.map".format(channel_name), "w") as f:
        for (k, v) in sorted(channel_suggest_map.items()):
            f.write("{0}:{1}\n".format(k, v))

    return FileResponse(
        "{0}.map".format(channel_name),
        media_type="application/octet-stream",
        filename="{0}.map".format(channel_name),
    )
