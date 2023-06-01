import logging
from pathlib import Path

from sqlalchemy import desc

import quetz
from quetz.database import get_db_manager

from . import db_models
from .api import router

logger = logging.getLogger("quetz")


@quetz.hookimpl
def register_router():
    return router


@quetz.hookimpl
def post_index_creation(raw_repodata: dict, channel_name, subdir):
    """Use available online keys to sign packages"""

    with get_db_manager() as db:
        query = (
            db.query(db_models.SigningKey)
            .join(db_models.RoleDelegation.keys)
            .filter(
                db_models.RoleDelegation.channel == channel_name,
                db_models.RoleDelegation.type == "pkg_mgr",
                db_models.SigningKey.private_key is not None,
            )
            .order_by(desc('time_created'))
            .all()
        )

        signatures = {}
        if query:
            import json

            from libmambapy import bindings as libmamba_api

            packages = raw_repodata.get("packages", {}) | raw_repodata.get(
                "packages.conda", {}
            )
            for name, metadata in packages.items():
                sig = libmamba_api.sign(
                    json.dumps(metadata, indent=2, sort_keys=True), query[0].private_key
                )
                if name not in signatures:
                    signatures[name] = {}

                signatures[name][query[0].public_key] = dict(signature=sig)

        logger.info(f"Signed {Path(channel_name) / subdir}")
        raw_repodata["signatures"] = signatures
