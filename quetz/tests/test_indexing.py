import pytest

from quetz.config import Config
from quetz.db_models import Channel
from quetz.tasks.indexing import update_indexes


@pytest.fixture
def local_channel(db):

    channel = Channel(name="test-local-channel")
    db.add(channel)
    db.commit()

    yield channel

    db.delete(channel)
    db.commit()


def test_update_indexes(config: Config, local_channel, dao):
    pkgstore = config.get_package_store()

    update_indexes(dao, pkgstore, local_channel.name)

    files = pkgstore.list_files(local_channel.name)

    base_files = [
        'channeldata.json',
        'index.html',
        'noarch/index.html',
        'noarch/repodata.json',
    ]

    expected_files = base_files.copy()

    for suffix in ['.bz2', '.gz']:
        expected_files.extend(s + suffix for s in base_files)

    assert sorted(files) == sorted(expected_files)
