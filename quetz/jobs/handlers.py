from quetz.metrics import tasks as metrics_tasks
from quetz.tasks import cleanup, indexing, mirror, reindexing

JOB_HANDLERS = {
    "synchronize": mirror.synchronize_packages,
    "synchronize_repodata": mirror.synchronize_packages,
    "validate_packages": indexing.validate_packages,
    "generate_indexes": indexing.update_indexes,
    "reindex": reindexing.reindex_packages_from_store,
    "synchronize_metrics": metrics_tasks.synchronize_metrics_from_mirrors,
    "pkgstore_cleanup": cleanup.cleanup_channel_db,
    "db_cleanup": cleanup.cleanup_temp_files,
    "pkgstore_cleanup_dry_run": cleanup.cleanup_channel_db,
    "db_cleanup_dry_run": cleanup.cleanup_temp_files,
}
