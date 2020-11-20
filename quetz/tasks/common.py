import requests
from fastapi import BackgroundTasks, HTTPException, status

from quetz import authorization, db_models
from quetz.config import Config
from quetz.dao import Dao
from quetz.rest_models import ChannelActionEnum

from . import assertions, mirror, reindexing


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


def execute_channel_action(
    action: str,
    channel: db_models.Channel,
    dao: Dao,
    auth: authorization.Rules,
    session: requests.Session,
    background_tasks: BackgroundTasks,
    config: Config,
):

    pkgstore = config.get_package_store()

    assert_channel_action(action, channel)

    user_id = auth.assert_user()

    if action == ChannelActionEnum.synchronize:
        auth.assert_synchronize_mirror(channel.name)

        mirror.synchronize_packages(
            channel, dao, pkgstore, auth, session, background_tasks
        )
    elif action == ChannelActionEnum.reindex:
        auth.assert_reindex_channel(channel.name)
        background_tasks.add_task(
            reindexing.reindex_packages_from_store, config, channel.name, user_id
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(f"Action {action} on channel {channel.name} is not implemented"),
        )
