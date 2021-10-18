from fastapi import HTTPException, status

import quetz
from quetz.dao import Dao
from quetz.authorization import OWNER

from .api import get_db_manager, router
from .db_models import TermsOfService, TermsOfServiceSignatures


@quetz.hookimpl
def register_router():
    return router


def check_for_signed_tos(user_id, user_role):
    with get_db_manager() as db:
        dao = Dao(db)
        user = dao.get_user(user_id)
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
                    detail = f"terms of service is not signed for {user.profile.name}"
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN, detail=detail
                    )
            else:
                return True


@quetz.hookimpl
def check_additional_permissions(user_id, user_role):
    return check_for_signed_tos(user_id, user_role)
