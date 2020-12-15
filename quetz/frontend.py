import logging
import os
import sys

from starlette.staticfiles import StaticFiles

from quetz.config import Config

config = Config()

logger = logging.getLogger('quetz')


def register_mock_routes(router):
    pass


def register(app, api_router):
    # mount frontend
    if hasattr(config, 'general_frontend_dir'):
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
