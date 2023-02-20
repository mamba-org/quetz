import os
import uuid
from tempfile import SpooledTemporaryFile
from typing import List, Union

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm.session import Session

from quetz import authorization, dao
from quetz.config import Config
from quetz.deps import get_dao, get_db, get_rules

from .db_models import TermsOfService, TermsOfServiceFile, TermsOfServiceSignatures

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
def get_current_tos(lang: Union[str, None] = None, db: Session = Depends(get_db)):
    current_tos = (
        db.query(TermsOfService).order_by(TermsOfService.time_created.desc()).first()
    )

    if current_tos is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="terms of service not found",
        )

    tos_files = []
    for tos_file in current_tos.files:
        f = pkgstore.serve_path("root", tos_file.filename)
        data_bytes = f.read()

        if lang is None or lang == tos_file.language:
            tos_files.append(
                {
                    "content": data_bytes.decode('utf-8'),
                    "filename": tos_file.filename,
                    "language": tos_file.language,
                }
            )

    if lang is not None and not tos_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"terms of service for language {lang} not found",
        )

    return {
        "id": str(uuid.UUID(bytes=current_tos.id)),
        "uploader_id": str(uuid.UUID(bytes=current_tos.uploader_id)),
        "files": tos_files,
        "time_created": current_tos.time_created,
    }


@router.get("/api/tos/status", status_code=201, tags=['Terms of Service'])
def get_current_tos_status(
    db: Session = Depends(get_db),
    dao: dao.Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    user_id = auth.assert_user()
    current_tos = (
        db.query(TermsOfService).order_by(TermsOfService.time_created.desc()).first()
    )
    if current_tos:
        signature = (
            db.query(TermsOfServiceSignatures)
            .filter(TermsOfServiceSignatures.user_id == user_id)
            .filter(TermsOfServiceSignatures.tos_id == current_tos.id)
            .one_or_none()
        )
        if signature:
            return {
                "tos_id": str(uuid.UUID(bytes=signature.tos_id)),
                "user_id": str(uuid.UUID(bytes=signature.user_id)),
                "time_created": signature.time_created,
            }
        else:
            return None
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="terms of service file not found",
        )


@router.post("/api/tos/sign", status_code=201, tags=['Terms of Service'])
def sign_current_tos(
    tos_id: str = "",
    db: Session = Depends(get_db),
    dao: dao.Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    user_id = auth.assert_user()
    user = dao.get_user(user_id)

    if user is None:
        raise RuntimeError(f"User '{user}' not found.")

    if tos_id:
        try:
            tos_id_bytes = uuid.UUID(tos_id).bytes
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{tos_id} is not a valid hexadecimal string",
            )
        terms_of_services = (
            db.query(TermsOfService).order_by(TermsOfService.time_created.desc()).all()
        )
        selected_tos = None
        for tos in terms_of_services:
            if tos.id == tos_id_bytes:
                selected_tos = tos
                break

        if not selected_tos:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"terms of service with id {tos_id} not found",
            )
    else:
        selected_tos = (
            db.query(TermsOfService)
            .order_by(TermsOfService.time_created.desc())
            .first()
        )

    if selected_tos:
        signature = (
            db.query(TermsOfServiceSignatures)
            .filter(TermsOfServiceSignatures.user_id == user_id)
            .filter(TermsOfServiceSignatures.tos_id == selected_tos.id)
            .one_or_none()
        )
        if signature:
            return (
                f"TOS already signed for {user.username}"
                f" at {signature.time_created}."
            )
        else:
            signature = TermsOfServiceSignatures(
                user_id=user_id, tos_id=selected_tos.id
            )
            db.add(signature)
            db.commit()
            return f"TOS signed for {user.username}"
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="terms of service file not found",
        )


@router.post("/api/tos/upload", status_code=201, tags=['Terms of Service'])
def upload_tos(
    lang: List[str] = Query(...),
    db: Session = Depends(get_db),
    auth: authorization.Rules = Depends(get_rules),
    tos_files: List[UploadFile] = File(...),
):
    user_id = auth.assert_server_roles(
        ["owner"], "To upload new Terms of Services you need to be a server owner."
    )

    if len(lang) != len(tos_files):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Number of languages '{lang}' does not "
                "match the number of uploaded files"
            ),
        )

    filenames = [post_file(tos_file) for tos_file in tos_files]

    tos_files = [
        TermsOfServiceFile(filename=filename, language=language)
        for filename, language in zip(filenames, lang)
    ]
    tos = TermsOfService(uploader_id=user_id, files=tos_files)

    db.add(tos)
    db.commit()
