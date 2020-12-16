import quetz

from .api import router


@quetz.hookimpl
def register_router():
    return router
