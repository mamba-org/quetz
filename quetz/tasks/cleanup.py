from quetz.dao import Dao
from quetz.pkgstores import PackageStore


def cleanup_channel_db(dao: Dao, channel_name: str, dry_run: bool):
    dao.cleanup_channel_db(channel_name, dry_run)


def cleanup_temp_files(pkgstore: PackageStore, channel_name: str, dry_run: bool):
    pkgstore.cleanup_temp_files(channel_name, dry_run)
