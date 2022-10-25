from fastapi import APIRouter, Depends, HTTPException, status
from passlib.hash import pbkdf2_sha256
from sqlalchemy.orm.session import Session

from quetz import authorization
from quetz.authorization import SERVER_MAINTAINER, SERVER_OWNER
from quetz.deps import get_db, get_rules

from .db_models import Credentials

router = APIRouter()


def _calculate_hash(value: str) -> str:
    """Calculate hash from value."""
    return pbkdf2_sha256.hash(value)


@router.get(
    "/api/sqlauth/credentials/{username}",
    tags=["sqlauth"],
)
def _get(
    username: str,
    auth: authorization.Rules = Depends(get_rules),
    db: Session = Depends(get_db),
) -> str:
    auth.assert_assign_user_role([SERVER_OWNER, SERVER_MAINTAINER])

    # Get user from db
    db_credentials = (
        db.query(Credentials).filter(Credentials.username == username).one_or_none()
    )
    if db_credentials is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {username} not found",
        )

    return username


@router.post("/api/sqlauth/credentials/{username}", tags=["sqlauth"])
def _create(
    username: str,
    password: str,
    auth: authorization.Rules = Depends(get_rules),
    db: Session = Depends(get_db),
) -> str:
    auth.assert_assign_user_role([SERVER_OWNER, SERVER_MAINTAINER])

    credentials = Credentials(
        username=username, password_hash=_calculate_hash(password)
    )
    db.add(credentials)
    db.commit()

    return username


@router.put("/api/sqlauth/credentials/{username}", tags=["sqlauth"])
def _update(
    username: str,
    password: str,
    auth: authorization.Rules = Depends(get_rules),
    db: Session = Depends(get_db),
) -> str:
    auth.assert_assign_user_role([SERVER_OWNER, SERVER_MAINTAINER])

    credentials = (
        db.query(Credentials).filter(Credentials.username == username).one_or_none()
    )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {username} not found",
        )
    credentials.password = _calculate_hash(password)
    db.commit()

    return username


@router.delete("/api/sqlauth/credentials/{username}", tags=["sqlauth"])
def _delete(
    username: str,
    auth: authorization.Rules = Depends(get_rules),
    db: Session = Depends(get_db),
) -> str:
    auth.assert_assign_user_role([SERVER_OWNER, SERVER_MAINTAINER])

    credentials = (
        db.query(Credentials).filter(Credentials.username == username).one_or_none()
    )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {username} not found",
        )
    db.delete(credentials)
    db.commit()
    return username


@router.delete("/api/sqlauth/credentials", tags=["sqlauth"])
def _reset(
    auth: authorization.Rules = Depends(get_rules), db: Session = Depends(get_db)
) -> None:
    auth.assert_assign_user_role([SERVER_OWNER, SERVER_MAINTAINER])

    db.query(Credentials).delete()
    db.commit()
