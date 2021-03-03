import logging
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status

from quetz import authorization, dao, db_models
from quetz.jobs.dao import JobsDao
from quetz.rest_models import ChannelActionEnum

from . import assertions

logger = logging.getLogger("quetz")


def assert_channel_action(action, channel):
    if action == ChannelActionEnum.synchronize:
        action_allowed = assertions.can_channel_synchronize(channel)
    elif action == ChannelActionEnum.synchronize_repodata:
        action_allowed = assertions.can_channel_synchronize(channel)
    elif action == ChannelActionEnum.validate_packages:
        action_allowed = assertions.can_channel_validate_package_cache(channel)
    elif action == ChannelActionEnum.generate_indexes:
        action_allowed = assertions.can_channel_reindex(channel)
    elif action == ChannelActionEnum.reindex:
        action_allowed = assertions.can_channel_reindex(channel)
    elif action == ChannelActionEnum.synchronize_metrics:
        action_allowed = assertions.can_channel_synchronize_metrics(channel)
    elif action == ChannelActionEnum.cleanup:
        action_allowed = assertions.can_cleanup(channel)
    elif action == ChannelActionEnum.cleanup_dry_run:
        action_allowed = assertions.can_cleanup(channel)
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
        db,
    ):
        from quetz.deps import get_config

        self.auth = auth
        self.db = db
        self.jobs_dao = JobsDao(db)
        self.dao = dao.Dao(db)
        self.pkgstore = get_config().get_package_store()

    def execute_channel_action(
        self,
        action: str,
        channel: db_models.Channel,
        start_at: Optional[datetime] = None,
        repeat_every_seconds: Optional[int] = None,
    ):
        auth = self.auth

        channel_name = channel.name
        channel_metadata = channel.load_channel_metadata()
        assert_channel_action(action, channel)

        user_id = auth.assert_user()

        if action == ChannelActionEnum.synchronize:
            auth.assert_synchronize_mirror(channel_name)
            extra_args = dict(
                channel_name=channel_name,
                includelist=channel_metadata.get('includelist', None),
                excludelist=channel_metadata.get('excludelist', None),
            )
            task = self.jobs_dao.create_job(
                action.encode('ascii'),
                user_id,
                extra_args=extra_args,
                start_at=start_at,
                repeat_every_seconds=repeat_every_seconds,
            )
        elif action == ChannelActionEnum.synchronize_repodata:
            auth.assert_synchronize_mirror(channel_name)
            extra_args = dict(
                channel_name=channel_name,
                use_repodata=True,
                includelist=channel_metadata.get('includelist', None),
                excludelist=channel_metadata.get('excludelist', None),
            )
            task = self.jobs_dao.create_job(
                action.encode('ascii'),
                user_id,
                extra_args=extra_args,
                start_at=start_at,
                repeat_every_seconds=repeat_every_seconds,
            )
        elif action == ChannelActionEnum.validate_packages:
            auth.assert_validate_package_cache(channel_name)
            extra_args = dict(channel_name=channel.name)
            task = self.jobs_dao.create_job(
                action.encode('ascii'),
                user_id,
                extra_args=extra_args,
                start_at=start_at,
                repeat_every_seconds=repeat_every_seconds,
            )
        elif action == ChannelActionEnum.generate_indexes:
            auth.assert_reindex_channel(channel_name)
            extra_args = dict(channel_name=channel.name)
            task = self.jobs_dao.create_job(
                action.encode('ascii'),
                user_id,
                extra_args=extra_args,
                start_at=start_at,
                repeat_every_seconds=repeat_every_seconds,
            )
        elif action == ChannelActionEnum.reindex:
            auth.assert_reindex_channel(channel_name)
            extra_args = dict(
                channel_name=channel_name,
            )
            task = self.jobs_dao.create_job(
                action.encode('ascii'),
                user_id,
                extra_args=extra_args,
                start_at=start_at,
                repeat_every_seconds=repeat_every_seconds,
            )
        elif action == ChannelActionEnum.synchronize_metrics:
            auth.assert_reindex_channel(channel_name)
            extra_args = dict(channel_name=channel.name)
            task = self.jobs_dao.create_job(
                action.encode('ascii'),
                user_id,
                extra_args=extra_args,
                start_at=start_at,
                repeat_every_seconds=repeat_every_seconds,
            )
        elif action in [ChannelActionEnum.cleanup, ChannelActionEnum.cleanup_dry_run]:
            auth.assert_channel_db_cleanup(channel_name)
            dry_run = action == ChannelActionEnum.cleanup_dry_run
            extra_args = dict(
                channel_name=channel_name,
                dry_run=dry_run,
            )
            task = self.jobs_dao.create_job(
                f"db_{action}".encode('ascii'),
                user_id,
                extra_args=extra_args,
                start_at=start_at,
                repeat_every_seconds=repeat_every_seconds,
            )
            task = self.jobs_dao.create_job(
                f"pkgstore_{action}".encode('ascii'),
                user_id,
                extra_args=extra_args,
                start_at=start_at,
                repeat_every_seconds=repeat_every_seconds,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=(
                    f"Action {action} on channel {channel.name} is not implemented"
                ),
            )
        return task
