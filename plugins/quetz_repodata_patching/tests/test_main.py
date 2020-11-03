import os

from quetz import indexing


def test_post_package_indexing(config, dao):

    pkgstore = config.get_package_store()
    indexing.update_indexes(dao, pkgstore, "my_channel")

    assert os.path.isfile(
        os.path.join(pkgstore.channels_dir, "my_channel", "noarch", "repodata.json")
    )
    assert os.path.isfile(
        os.path.join(
            pkgstore.channels_dir, "my_channel", "noarch", "repodata_from_packages.json"
        )
    )
