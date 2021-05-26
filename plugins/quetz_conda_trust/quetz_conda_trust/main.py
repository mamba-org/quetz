import quetz
from .api import router

@quetz.hookimpl
def register_router():
    return router

@quetz.hookimpl
def post_add_package_version(version, condainfo):
    # Implement your logic
    pass
