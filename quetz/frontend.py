import logging
import os
import sys
from pathlib import Path

import jinja2
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from quetz.config import Config

config = Config()

logger = logging.getLogger('quetz')

mock_router = APIRouter()
catchall_router = APIRouter()


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
    return {
        "settings": [
            {
                "id": "@jupyterlab/apputils-extension:themes",
                "raw": "{\n    // Theme\n    // @jupyterlab/apputils-extension:themes\n    // Theme manager settings.\n    // *************************************\n\n    // Selected Theme\n    // Application-level visual styling theme\n    \"theme\": \"JupyterLab Dark\",\n\n    // Scrollbar Theming\n    // Enable/disable styling of the application scrollbars\n    \"theme-scrollbars\": true\n}",
                "schema": {
                    "title": "Theme",
                    "jupyter.lab.setting-icon-label": "Theme Manager",
                    "description": "Theme manager settings.",
                    "type": "object",
                    "additionalProperties": False,
                    "definitions": {
                        "cssOverrides": {
                            "type": "object",
                            "additionalProperties": False,
                            "description": "The description field of each item is the CSS property that will be used to validate an override's value",
                            "properties": {
                                "code-font-size": {
                                    "type": ["string", "null"],
                                    "description": "font-size",
                                },
                                "content-font-size1": {
                                    "type": ["string", "null"],
                                    "description": "font-size",
                                },
                                "ui-font-size1": {
                                    "type": ["string", "null"],
                                    "description": "font-size",
                                },
                            },
                        }
                    },
                    "properties": {
                        "theme": {
                            "type": "string",
                            "title": "Selected Theme",
                            "description": "Application-level visual styling theme",
                            "default": "JupyterLab Dark",
                        },
                        "theme-scrollbars": {
                            "type": "boolean",
                            "title": "Scrollbar Theming",
                            "description": "Enable/disable styling of the application scrollbars",
                            "default": False,
                        },
                        "overrides": {
                            "title": "Theme CSS Overrides",
                            "description": "Override theme CSS variables by setting key-value pairs here",
                            "$ref": "#/definitions/cssOverrides",
                            "default": {
                                "code-font-size": None,
                                "content-font-size1": None,
                                "ui-font-size1": None,
                            },
                        },
                    },
                },
                "settings": {"theme": "JupyterLab Dark", "theme-scrollbars": True},
                "version": "2.2.6",
            },
        ]
    }


@mock_router.get('/quetz-themes/{resource:path}', include_in_schema=False)
def get_theme(resource: str):
    final_path = os.path.join(frontend_dir, resource)
    logger.info(f"Getting file from {frontend_dir}")
    logger.info(final_path)
    if os.path.exists(final_path):
        return FileResponse(path=final_path)
    else:
        raise HTTPException(status_code=404)


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

    app.include_router(mock_router, prefix="/jlabmock")

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
