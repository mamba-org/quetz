import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

import quetz.authentication.base as auth_base
from quetz import rest_models
from quetz.config import Config, ConfigEntry, ConfigSection
from quetz.dao import Dao
from quetz.deps import get_config, get_db

logger = logging.getLogger("quetz.googleiam")


def email_to_channel_name(email):
    name = email.split("@")[0]
    name = name.replace(".", "-")
    name = name.replace("_", "-")
    return name


class GoogleIAMMiddleware(BaseHTTPMiddleware):
    """
    Handles Google IAM headers and authorizes users based on the
    Google IAM headers.
    """

    def __init__(self, app, config: Config):
        if config is not None:
            self.configure(config)
        self.last_checked = dict()
        super().__init__(app)

    def configure(self, config: Config):
        config.register(
            [
                ConfigSection(
                    "googleiam",
                    [
                        ConfigEntry("server_admin_emails", list, default=[]),
                    ],
                )
            ]
        )

        # load configuration values
        if config.configured_section("googleiam"):
            self.server_admin_emails = config.googleiam_server_admin_emails
        else:
            raise Exception("Google IAM is not configured")

    async def dispatch(self, request, call_next):
        # Check if the session has a specific key, for example 'count'.
        # If it does, increment its value. If it doesn't, set it to 1.
        count = request.session.get("count", 0)
        request.session["count"] = count + 1

        user_id = request.headers.get("x-goog-authenticated-user-id")
        email = request.headers.get("x-goog-authenticated-user-email")

        if user_id and email:
            db = next(get_db(get_config()))
            dao = Dao(db)

            _, email = email.split(":", 1)
            _, user_id = user_id.split(":", 1)

            user = dao.get_user_by_username(email)
            if not user:
                email_data: auth_base.Email = {
                    "email": email,
                    "verified": True,
                    "primary": True,
                }
                user = dao.create_user_with_profile(
                    email, "google", user_id, email, "", None, True, [email_data]
                )
            user_channel = email_to_channel_name(email)

            if dao.get_channel(email_to_channel_name(user_channel)) is None:
                logger.info(f"Creating channel for user: {user_channel}")
                channel = rest_models.Channel(
                    name=user_channel,
                    private=False,
                    description="Channel for user: " + email,
                )
                dao.create_channel(channel, user.id, "owner")

            self.google_role_for_user(user_id, dao)
            user_id = uuid.UUID(bytes=user.id)
            # drop the db and dao to remove the connection
            del db, dao
            # we also need to find the role of the user
            request.session['identity_provider'] = "dummy"
            request.session["user_id"] = str(user_id)
        else:
            request.session["user_id"] = None
            request.session["identity_provider"] = None

        response = await call_next(request)
        return response

    def google_role_for_user(self, user_id, dao):
        if not user_id:
            return

        if user_id in self.server_admin_emails:
            logger.info(f"User {user_id} is server admin")
            dao.set_user_role(user_id, "owner")
        else:
            logger.info(f"User {user_id} is not a server admin")
            dao.set_user_role(user_id, "member")


def middleware():
    return GoogleIAMMiddleware
