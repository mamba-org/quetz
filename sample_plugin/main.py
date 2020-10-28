from fastapi import APIRouter

import quetz


@quetz.hookimpl
def register_router():
    router = APIRouter()

    @router.get("/test-plugin")
    def get_plugin():
        return "hello world"

    return router


@quetz.hookimpl
def extract_package_metadata(filehandler):
    return "quetz-sync", {"synchronized": True, "time_modified": 0}
