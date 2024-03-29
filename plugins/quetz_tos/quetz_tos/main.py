from fastapi import HTTPException, status

import quetz
from quetz.authorization import OWNER
from quetz.dao import Dao

from .api import router
from .db_models import TermsOfService, TermsOfServiceSignatures


@quetz.hookimpl
def register_router():
    return router


def check_for_signed_tos(db, user_id, user_role):
    dao = Dao(db)
    user = dao.get_user(user_id)
    if user:
        if user_role == OWNER:
            return True
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
                    return True
                else:
                    detail = f"terms of service is not signed for {user.username}"
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN, detail=detail
                    )
            else:
                return True
    else:
        detail = f"user with id {user_id} not found"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@quetz.hookimpl
def check_additional_permissions(db, user_id, user_role):
    return check_for_signed_tos(db, user_id, user_role)
