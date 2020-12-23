import logging

from fastapi import HTTPException, status

from quetz import authorization, db_models
from quetz.metrics import tasks as metrics_tasks
from quetz.rest_models import ChannelActionEnum

from . import assertions, indexing, mirror, reindexing
from .workers import AbstractWorker

logger = logging.getLogger("quetz")


def assert_channel_action(action, channel):
    if action == ChannelActionEnum.synchronize:
        action_allowed = assertions.can_channel_synchronize(channel)
    elif action == ChannelActionEnum.validate_packages:
        action_allowed = assertions.can_channel_validate_package_cache(channel)
    elif action == ChannelActionEnum.generate_indexes:
        action_allowed = assertions.can_channel_reindex(channel)
    elif action == ChannelActionEnum.reindex:
        action_allowed = assertions.can_channel_reindex(channel)
    elif action == ChannelActionEnum.synchronize_metrics:
        action_allowed = assertions.can_channel_synchronize_metrics(channel)
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

    def execute_channel_action(self, action: str, channel: db_models.Channel, **kwargs):
        auth = self.auth

        channel_name = channel.name

        assert_channel_action(action, channel)

        user_id = auth.assert_user()

        if action == ChannelActionEnum.synchronize:
            auth.assert_synchronize_mirror(channel_name)
            include = kwargs.get('include')
            package_list = kwargs.get('package_list')
            self.worker.execute(
                mirror.synchronize_packages,
                channel_name=channel_name,
                package_list=package_list,
                include=include,
            )
        elif action == ChannelActionEnum.validate_packages:
            auth.assert_validate_package_cache(channel_name)
            self.worker.execute(indexing.validate_packages, channel_name=channel.name)
        elif action == ChannelActionEnum.generate_indexes:
            auth.assert_reindex_channel(channel_name)
            self.worker.execute(indexing.update_indexes, channel_name=channel.name)
        elif action == ChannelActionEnum.reindex:
            auth.assert_reindex_channel(channel_name)
            self.worker.execute(
                reindexing.reindex_packages_from_store,
                channel_name=channel_name,
                user_id=user_id,
            )
        elif action == ChannelActionEnum.synchronize_metrics:
            auth.assert_reindex_channel(channel_name)
            self.worker.execute(
                metrics_tasks.synchronize_metrics_from_mirrors,
                channel_name=channel_name,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=(
                    f"Action {action} on channel {channel.name} is not implemented"
                ),
            )
