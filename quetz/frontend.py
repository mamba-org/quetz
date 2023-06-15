import logging
import os
import sys

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from importlib_metadata import entry_points

from quetz import authorization
from quetz.config import Config
from quetz.dao import Dao
from quetz.deps import get_dao, get_rules, get_session

config = Config()

logger = logging.getLogger('quetz')

catchall_router = APIRouter()

mock_settings_dict = None
frontend_dir = ""
config_data: dict


def _under_frontend_dir(path):
    """
    Check that path is under frontend_dir

    NOTE: os.path.abspath may seem unnecessary, but os.path.commonpath does not
    appear to handle relative paths as you would expect:

    >>> commonpath([abspath('../quetz/quetz'), abspath('quetz')])
    '/home/username/quetz/quetz'
    >>> commonpath(['../quetz/quetz', 'quetz'])
    ''
    """
    path = os.path.abspath(os.path.join(frontend_dir, path))
    fdir = os.path.abspath(frontend_dir)
    return os.path.commonpath([path, fdir]) == fdir


@catchall_router.get('/{resource:path}', include_in_schema=False)
def static(
    resource: str,
    session: dict = Depends(get_session),
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    is_api_or_auth = resource.startswith(('api/', 'auth/'))
    if is_api_or_auth:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if "." not in resource:
        logger.info(f"returning index.html for {resource}")
        return FileResponse(path=os.path.join(frontend_dir, "index.html"))
    else:
        if not _under_frontend_dir(resource):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        file = os.path.join(frontend_dir, resource)
        if os.path.exists(file):
            return FileResponse(path=file)
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


def register(app):
    frontend_plugins = []
    for entry_point in entry_points().select(group='quetz.frontend'):
        frontend_plugins.append(entry_point)

    if len(frontend_plugins) > 1:
        logger.warning(
            "Multiple frontend plugins found!"
            f"{', '.join([str(fp) for fp in frontend_plugins])}\n"
            "Using last found."
        )

    if frontend_plugins:
        print("Register frontend hooks: ", frontend_plugins)
        logger.info(f"Loading frontend plugin: {frontend_plugins[-1]}")
        frontend_plugin = frontend_plugins[-1].load()
        return frontend_plugin.register(app)

    global frontend_dir
    global config_data

    # TODO do not add this in the final env, use nginx to route to static files
    app.include_router(catchall_router)

    if hasattr(config, 'general_frontend_dir') and config.general_frontend_dir:
        frontend_dir = config.general_frontend_dir
        logger.info(f"Configured frontend found: {config.general_frontend_dir}")
    elif os.path.isfile(f"{sys.prefix}/share/quetz/frontend/index.html"):
        logger.info("installed frontend found")
        frontend_dir = f"{sys.prefix}/share/quetz/frontend/"
    else:
        logger.info("Using basic fallback frontend")
        frontend_dir = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "basic_frontend"
        )
