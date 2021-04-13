import json
import logging
import os
import sys
from pathlib import Path

import jinja2
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from starlette.staticfiles import StaticFiles

from quetz import authorization, rest_models
from quetz.authentication import AuthenticatorRegistry
from quetz.config import Config
from quetz.dao import Dao
from quetz.deps import get_dao, get_rules, get_session

config = Config()

logger = logging.getLogger('quetz')

mock_router = APIRouter()
catchall_router = APIRouter()

mock_settings_dict = None
frontend_dir = ""
index_template = None
config_data: dict


@mock_router.get('/api/sessions', include_in_schema=False)
def mock_sessions():
    return []


@mock_router.get('/api/kernels', include_in_schema=False)
def mock_kernels():
    return []


@mock_router.get('/api/kernelspecs', include_in_schema=False)
def mock_kernelspecs():
    return []


@mock_router.get('/api/settings', include_in_schema=False)
def mock_settings():
    return mock_settings_dict


@mock_router.get('/quetz-themes/{resource:path}', include_in_schema=False)
def get_theme(resource: str):
    final_path = os.path.join(frontend_dir, resource)
    logger.info(f"Getting file from {frontend_dir}")
    logger.info(final_path)
    if os.path.exists(final_path):
        return FileResponse(path=final_path)
    else:
        raise HTTPException(status_code=404)


def render_index(config):
    global mock_settings_dict
    global index_template

    static_dir = config.general_frontend_dir

    logger.info("Rendering index.html!")
    static_dir = Path(static_dir)
    if (static_dir / ".." / "templates").exists():
        with open(static_dir / "index.html") as fi:
            index_template = jinja2.Template(fi.read())

        with open(static_dir / ".." / "templates" / "settings.json") as fi:
            settings_template = json.load(fi)

        with open(static_dir / ".." / "templates" / "default_settings.json") as fi:
            default_settings = fi.read()

        for setting in settings_template["settings"]:
            if setting["id"] == '@jupyterlab/apputils-extension:themes':
                setting["raw"] = default_settings

        with open(os.path.join(static_dir, "index.html"), "w") as fo:
            fo.write(index_template.render(page_config=config_data))

        mock_settings_dict = settings_template
        with open(static_dir / "settings.json", "w") as fo:
            fo.write(json.dumps(settings_template))


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
    elif ".." in resource:  # Don't serve relative paths
        return FileResponse(path=os.path.join(frontend_dir, "index.html"))
    else:
        return FileResponse(path=os.path.join(frontend_dir, resource))


def get_rendered_index(config_data, profile, index_template):
    config_data["logged_in_user_profile"] = rest_models.Profile.from_orm(profile).json()
    logger.info(f"Page config: {config_data}")
    index_rendered = index_template.render(page_config=config_data)
    return index_rendered


def register(app):
    # TODO fix, don't put under /api/
    # This is to help the jupyterlab-based frontend to not
    # have any 404 requests.
    global frontend_dir
    global config_data

    auth_registry = AuthenticatorRegistry()
    google_login_available = auth_registry.is_registered("google")
    github_login_available = auth_registry.is_registered("github")
    gitlab_login_available = auth_registry.is_registered("gitlab")

    config_data = {
        "appName": "Quetz – the fast conda package server!",
        "baseUrl": "/jlabmock/",
        "github_login_available": github_login_available,
        "gitlab_login_available": gitlab_login_available,
        "google_login_available": google_login_available,
    }

    logger.info(f"Frontend config: {config_data}")

    app.include_router(mock_router, prefix="/jlabmock")

    # TODO do not add this in the final env, use nginx to route
    #      to static files
    app.include_router(catchall_router)
    # mount frontend
    if hasattr(config, 'general_frontend_dir') and config.general_frontend_dir:
        render_index(config)
        frontend_dir = config.general_frontend_dir
        logger.info(f"Configured frontend found: {config.general_frontend_dir}")
    elif os.path.isfile("../quetz_frontend/dist/index.html"):
        logger.info("dev frontend found")
        frontend_dir = "../quetz_frontend/dist"
    elif os.path.isfile(f"{sys.prefix}/share/quetz/frontend/index.html"):
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
