import os
from tempfile import SpooledTemporaryFile

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from sqlalchemy.orm.session import Session

from quetz import dao
from quetz import authorization
from quetz.config import Config
from quetz.deps import get_rules, get_db, get_dao

from .db_models import TermsOfService, TermsOfServiceSignatures

router = APIRouter()
config = Config()

pkgstore = config.get_package_store()

def post_file(file):
    if type(file.file) is SpooledTemporaryFile and not hasattr(file, "seekable"):
        file.file.seekable = file.file._file.seekable

    file.file.seek(0, os.SEEK_END)
    file.file.seek(0)

    # channel_name is passed as "root" since we want to upload the file
    # in a host-wide manner i.e. independent of individual channels.
    # Azure and S3 necessarily require the creation of `containers` and `buckets`
    # (mapped to individual channels) before we can upload a file there.
    # Hence, the container / bucket will be `root`
    pkgstore.add_file(file.file.read(), "root", file.filename)
    return file.filename

@router.get("/api/tos", tags=['Terms of Service'])
def get_current_tos(db: Session = Depends(get_db)):
    current_tos = db.query(TermsOfService).order_by(TermsOfService.time_created.desc()).first()
    if current_tos:
        f = pkgstore.serve_path("root", current_tos.filename)
        data_bytes = f.read()
        return data_bytes
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"terms of service file not found",
        )

@router.post("/api/tos/sign", status_code=201, tags=['Terms of Service'])
def sign_current_tos(
    db: Session = Depends(get_db),
    dao: dao.Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    user_id = auth.assert_user()
    user = dao.get_user(user_id)
    current_tos = db.query(TermsOfService).order_by(TermsOfService.time_created.desc()).first()
    if current_tos:
        signature = db.query(TermsOfServiceSignatures).filter(TermsOfServiceSignatures.user_id == user_id).filter(TermsOfServiceSignatures.tos_id == current_tos.id).one_or_none()
        if signature:
            return f"TOS already signed for {user_id} at {signature.time_created}."
        else:
            signature = TermsOfServiceSignatures(user_id=user_id, tos_id=current_tos.id)
            db.add(signature)
            db.commit()
            return f"TOS signed for {user.profile.name}"
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"terms of service file not found",
        )

@router.post("/api/tos/upload", status_code=201, tags=['Terms of Service'])
def upload_tos(
    db: Session = Depends(get_db),
    auth: authorization.Rules = Depends(get_rules),
    tos_file: UploadFile = File(...),
):
    user_id = auth.assert_server_roles(["owner"], "To upload new Terms of Services you need to be a server owner.")
    filename = post_file(tos_file)
    tos = TermsOfService(uploader_id=user_id, filename=filename)
    db.add(tos)
    db.commit()
