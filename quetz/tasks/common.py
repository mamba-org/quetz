import logging

from fastapi import HTTPException, status
from quetz import authorization, dao, db_models
from quetz.jobs.dao import JobsDao
from quetz.main import pkgstore
from quetz.metrics import tasks as metrics_tasks
from quetz.rest_models import ChannelActionEnum

from . import assertions, indexing, mirror, reindexing
from .workers import AbstractWorker

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
        db,
    ):
        self.auth = auth
        self.worker = worker
        self.db = db
        self.jobs_dao = JobsDao(db)
        self.dao = dao.Dao(db)
        self.pkgstore = pkgstore

    def execute_channel_action(self, action: str, channel: db_models.Channel):
        auth = self.auth

        channel_name = channel.name
        channel_metadata = channel.load_channel_metadata()
        assert_channel_action(action, channel)

        user_id = auth.assert_user()

        if action == ChannelActionEnum.synchronize:
            auth.assert_synchronize_mirror(channel_name)
            task = self.jobs_dao.create_task(action.encode('ascii'), user_id)
            self.worker.execute(
                mirror.synchronize_packages,
                channel_name=channel_name,
                includelist=channel_metadata.get('includelist', None),
                excludelist=channel_metadata.get('excludelist', None),
                task_id=task.id,
            )
        elif action == ChannelActionEnum.synchronize_repodata:
            auth.assert_synchronize_mirror(channel_name)
            task = self.jobs_dao.create_task(action.encode('ascii'), user_id)
            self.worker.execute(
                mirror.synchronize_packages,
                channel_name=channel_name,
                use_repodata=True,
                includelist=channel_metadata.get('includelist', None),
                excludelist=channel_metadata.get('excludelist', None),
                task_id=task.id,
            )
        elif action == ChannelActionEnum.validate_packages:
            auth.assert_validate_package_cache(channel_name)
            task = self.jobs_dao.create_task(action.encode('ascii'), user_id)
            self.worker.execute(
                indexing.validate_packages,
                channel_name=channel.name,
                task_id=task.id,
            )
        elif action == ChannelActionEnum.generate_indexes:
            auth.assert_reindex_channel(channel_name)
            task = self.jobs_dao.create_task(action.encode('ascii'), user_id)
            self.worker.execute(
                indexing.update_indexes, channel_name=channel.name, task_id=task.id
            )
        elif action == ChannelActionEnum.reindex:
            auth.assert_reindex_channel(channel_name)
            task = self.jobs_dao.create_task(action.encode('ascii'), user_id)
            self.worker.execute(
                reindexing.reindex_packages_from_store,
                channel_name=channel_name,
                user_id=user_id,
                task_id=task.id,
            )
        elif action == ChannelActionEnum.synchronize_metrics:
            auth.assert_reindex_channel(channel_name)
            task = self.jobs_dao.create_task(action.encode('ascii'), user_id)
            self.worker.execute(
                metrics_tasks.synchronize_metrics_from_mirrors,
                channel_name=channel_name,
                task_id=task.id,
            )
        elif action == ChannelActionEnum.cleanup:
            auth.assert_channel_db_cleanup(channel_name)
            task = self.jobs_dao.create_task(f"db_{action}".encode('ascii'), user_id)
            self.worker.execute(
                self.dao.cleanup_channel_db,
                channel_name=channel_name,
                task_id=task.id,
            )
            task = self.jobs_dao.create_task(
                f"pkgstore_{action}".encode('ascii'), user_id
            )
            self.worker.execute(
                self.pkgstore.cleanup_temp_files,
                channel=channel_name,
                task_id=task.id,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=(
                    f"Action {action} on channel {channel.name} is not implemented"
                ),
            )
        return task
