import quetz
from .api import router
from .api import get_db_manager
from .db_models import TermsOfService, TermsOfServiceSignatures


@quetz.hookimpl
def register_router():
    return router


@quetz.hookimpl
def check_for_signed_tos(user_id):
    with get_db_manager() as db:
        selected_tos = db.query(TermsOfService).order_by(TermsOfService.time_created.desc()).first()
        if selected_tos:
            signature = db.query(TermsOfServiceSignatures).filter(TermsOfServiceSignatures.user_id == user_id).filter(TermsOfServiceSignatures.tos_id == selected_tos.id).one_or_none()
            if signature:
                return True
            else:
                return False
        else:
            # what if there doesn't exist a terms of service but the plugin is installed?
            # treating it as if the plugin is not installed
            return True

