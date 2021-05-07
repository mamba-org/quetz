import json
import logging
import os
import sys
from pathlib import Path
import pkg_resources
import jinja2
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from starlette.staticfiles import StaticFiles

from quetz import authorization, rest_models
from quetz.authentication import AuthenticatorRegistry
from quetz.config import Config, get_plugin_manager
from quetz.dao import Dao
from quetz.deps import get_dao, get_rules, get_session

config = Config()

logger = logging.getLogger('quetz')

catchall_router = APIRouter()

mock_settings_dict = None
frontend_dir = ""
index_template = None
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
    path = os.path.abspath(path)
    fdir = os.path.abspath(frontend_dir)

    return os.path.commonpath([path, fdir]) == fdir


@catchall_router.get('/{resource:path}', include_in_schema=False)
def static(
    resource: str,
    session: dict = Depends(get_session),
    dao: Dao = Depends(get_dao),
    auth: authorization.Rules = Depends(get_rules),
):
    user_id = auth.get_user()

    if "." not in resource:
        if index_template is None or user_id is None:
            return FileResponse(path=os.path.join(frontend_dir, "index.html"))
        else:
            profile = dao.get_profile(user_id)
            if profile is not None:
                index_rendered = get_rendered_index(
                    config_data, profile, index_template
                )
                return HTMLResponse(content=index_rendered, status_code=200)
            else:
                return FileResponse(path=os.path.join(frontend_dir, "index.html"))
    elif not _under_frontend_dir(resource):
        return FileResponse(path=os.path.join(frontend_dir, "index.html"))
    else:
        return FileResponse(path=os.path.join(frontend_dir, resource))


def get_rendered_index(config_data, profile, index_template):
    config_data["logged_in_user_profile"] = rest_models.Profile.from_orm(profile).json()
    logger.info(f"Page config: {config_data}")
    index_rendered = index_template.render(page_config=config_data)
    return index_rendered


def register(app):
    frontend_plugins = []
    for entry_point in pkg_resources.iter_entry_points('quetz.frontend'):
        frontend_plugins.append(entry_point)

    if len(frontend_plugins) > 1:
        logger.warning(f"Multiple frontend plugins found! {', '.join(frontend_plugins)}\nUsing last found.")

    if frontend_plugins:
        print("Register frontend hooks: ", frontend_plugins)
        logger.info(f"Loading frontend plugin: {frontend_plugins[-1]}")
        frontend_plugin = frontend_plugins[-1].load()
        return frontend_plugin.register(app)

    # TODO fix, don't put under /api/
    # This is to help the jupyterlab-based frontend to not
    # have any 404 requests.
    global frontend_dir
    global config_data


    logger.info(f"Frontend config: {config_data}")

    # TODO do not add this in the final env, use nginx to route
    #      to static files
    app.include_router(catchall_router)

    # mount frontend
    if os.path.isfile(f"{sys.prefix}/share/quetz/frontend/index.html"):
        logger.info("installed frontend found")
        frontend_dir = f"{sys.prefix}/share/quetz/frontend/"
    else:
        logger.info("basic frontend")
        frontend_dir = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "basic_frontend"
        )

    app.mount(
        "/",
        StaticFiles(directory=frontend_dir, html=True),
        name="frontend",
    )
