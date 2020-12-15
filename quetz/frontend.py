import logging
import os
import sys
from pathlib import Path

import jinja2
from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from quetz.config import Config

config = Config()

logger = logging.getLogger('quetz')

mock_router = APIRouter()
catchall_router = APIRouter()


@mock_router.get('/sessions', include_in_schema=False)
def mock_sessions():
    return []


@mock_router.get('/kernels', include_in_schema=False)
def mock_kernels():
    return []


@mock_router.get('/kernelspecs', include_in_schema=False)
def mock_kernelspecs():
    return []


def render_index(static_dir):
    config_data = {
        "appName": "Quetz – the fast conda package server!",
        "baseUrl": "/jlabmock/",
    }

    logger.info("Rendering index.html!")
    static_dir = Path(static_dir)
    if (static_dir / ".." / "templates").exists():
        with open(static_dir / ".." / "templates" / "index.html") as fi:
            index_template = jinja2.Template(fi.read())
        logger.info(f"Page config: {config_data}")
        index_rendered = index_template.render(page_config=config_data)
        with open(static_dir / "index.html", "w") as fo:
            fo.write(index_rendered)


frontend_dir = ""


@catchall_router.get('/{resource}', include_in_schema=False)
def static(resource: str):
    if "." not in resource:
        return FileResponse(path=os.path.join(frontend_dir, "index.html"))
    else:
        return FileResponse(path=os.path.join(frontend_dir, resource))


def register(app):
    # TODO fix, don't put under /api/
    # This is to help the jupyterlab-based frontend to not
    # have any 404 requests.
    global frontend_dir

    app.include_router(mock_router, prefix="/jlabmock/api")

    # TODO do not add this in the final env, use nginx to route
    #      to static files
    app.include_router(catchall_router)
    # mount frontend
    if hasattr(config, 'general_frontend_dir') and config.general_frontend_dir:
        render_index(config.general_frontend_dir)
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
