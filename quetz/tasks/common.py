import logging

from fastapi import HTTPException, status

from quetz import authorization, db_models
from quetz.rest_models import ChannelActionEnum

from . import assertions, mirror, reindexing
from .workers import AbstractWorker

logger = logging.getLogger("quetz")


def assert_channel_action(action, channel):
    if action == ChannelActionEnum.synchronize:
        action_allowed = assertions.can_channel_synchronize(channel)
    elif action == ChannelActionEnum.reindex:
        action_allowed = assertions.can_channel_reindex(channel)
    else:
        action_allowed = False

    if not action_allowed:
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail=f"Action {action} not allowed for channel {channel.name}",
        )


class Task:
    def __init__(
        self,
        auth: authorization.Rules,
        worker: AbstractWorker,
    ):
        self.auth = auth
        self.worker = worker

    def execute_channel_action(self, action: str, channel: db_models.Channel):
        auth = self.auth

        channel_name = channel.name

        assert_channel_action(action, channel)

        user_id = auth.assert_user()

        if action == ChannelActionEnum.synchronize:
            auth.assert_synchronize_mirror(channel_name)

            self.worker._execute_function(mirror.synchronize_packages, channel_name)
        elif action == ChannelActionEnum.reindex:
            auth.assert_reindex_channel(channel_name)
            self.worker._execute_function(
                reindexing.reindex_packages_from_store,
                channel_name=channel_name,
                user_id=user_id,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=(
                    f"Action {action} on channel {channel.name} is not implemented"
                ),
            )
