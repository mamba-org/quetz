import logging
import os
import sys
from pathlib import Path

import jinja2
from fastapi import APIRouter
from starlette.staticfiles import StaticFiles

from quetz.config import Config

config = Config()

logger = logging.getLogger('quetz')

mock_router = APIRouter()


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


def register(app):
    # TODO fix, don't put under /api/
    # This is to help the jupyterlab-based frontend to not
    # have any 404 requests.
    app.include_router(mock_router, prefix="/jlabmock/api")

    # mount frontend
    if hasattr(config, 'general_frontend_dir') and config.general_frontend_dir:
        render_index(config.general_frontend_dir)
        logger.info(f"Configured frontend found: {config.general_frontend_dir}")
        app.mount(
            "/",
            StaticFiles(directory=config.general_frontend_dir, html=True),
            name="frontend",
        )
    elif os.path.isfile("../quetz_frontend/dist/index.html"):
        logger.info("dev frontend found")
        app.mount(
            "/",
            StaticFiles(directory="../quetz_frontend/dist", html=True),
            name="frontend",
        )
    elif os.path.isfile(f"{sys.prefix}/share/quetz/frontend/index.html"):
        logger.info("installed frontend found")
        app.mount(
            "/",
            StaticFiles(directory=f"{sys.prefix}/share/quetz/frontend/", html=True),
            name="frontend",
        )
    else:
        logger.info("basic frontend")
        basic_frontend_dir = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "basic_frontend"
        )
        app.mount(
            "/", StaticFiles(directory=basic_frontend_dir, html=True), name="frontend"
        )
