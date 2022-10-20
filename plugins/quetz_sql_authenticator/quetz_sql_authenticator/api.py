import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm.session import Session

from quetz.config import Config
from quetz.deps import get_db

from rest_models import Credential

router = APIRouter()

 # TODO take care of auth

@router.get("/api/channels/{channel_name}/{subdir}/conda-suggest")
def get_conda_suggest(channel_name, subdir, db: Session = Depends(get_db)):
    map_filename = "{0}.{1}.map".format(channel_name, subdir)
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

import click
from passlib.hash import pbkdf2_sha256

from quetz.database import get_db_manager

from .db_models import Credentials


def _calculate_hash(value: str) -> str:
    """Calculate hash from value."""
    return pbkdf2_sha256.hash(value)

@router.get(
    "/api/sqlauth/credentials/{username}",
    response_model=Credential,
    tags=["sqlauth"],
)
def _get():
    # Get user from db
    db_credentials = db.query(Credentials).filter(Credentials.username == username).one_or_none()
    if db_credentials is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credentials for {username} not found",
        )
    # Return user
    credentials = Credential(username)
    return credentials

@router.post("/api/sqlauth/credentials/{username}")
def _create(password: str) -> None:
    credentials = Credentials(username=username, password=_calculate_hash(password))
    with get_db_manager() as db:
        db.add(credentials)
        db.commit()
    click.echo(f"INFO: User '{username}' created successfully.")


@router.put("/api/sqlauth/credentials/{username}")
def _update(password: str) -> None:
    with get_db_manager() as db:
        credentials = (
            db.query(Credentials).filter(Credentials.username == username).one_or_none()
        )
        if credentials is None:
            raise click.ClickException(f"ERROR: User '{username}' not found.")
        credentials.password = _calculate_hash(password)
        db.commit()
    click.echo(f"INFO: User '{username}' successfully updated.")


@router.delete("/api/sqlauth/credentials/{username}")
def _delete() -> None:
    with get_db_manager() as db:
        credentials = (
            db.query(Credentials).filter(Credentials.username == username).one_or_none()
        )
        if credentials is None:
            raise click.ClickException(f"ERROR: User '{username}' not found.")
        db.delete(credentials)
        db.commit()
    click.echo(f"INFO: User '{username}' successfully deleted.")


@router.get("/api/sqlauth/reset")
def _reset() -> None:
    with get_db_manager() as db:
        credentials_count = db.query(Credentials).count()
    click.echo(f"WARNING: Resetting the table will delete {credentials_count} users.")
    if click.confirm("Are you sure you want to reset the table?"):
        with get_db_manager() as db:
            db.query(Credentials).delete()
            db.commit()
        click.echo("INFO: Table reset successful.")
    else:
        click.echo("INFO: Table reset aborted.")
