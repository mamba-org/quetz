import os
import tempfile

import pytest

from quetz.pkgstores import LocalStore, S3Store

s3_config = {
    'key': os.environ.get("S3_ACCESS_KEY"),
    'secret': os.environ.get("S3_SECRET_KEY"),
    'url': os.environ.get("S3_ENDPOINT"),
    'region': os.environ.get("S3_REGION"),
    'bucket_prefix': "test",
    'bucket_suffix': "",
}


def test_local_store():

    pkgdir = tempfile.mkdtemp()
    pkg_store = LocalStore({'channels_dir': pkgdir})

    pkg_store.add_file("content", "my-channel", "test.txt")
    pkg_store.add_file("content", "my-channel", "test_2.txt")

    files = pkg_store.list_files("my-channel")

    assert files == ["test.txt", "test_2.txt"]

    pkg_store.delete_file("my-channel", "test.txt")

    files = pkg_store.list_files("my-channel")
    assert files == ["test_2.txt"]


@pytest.mark.skipif(not s3_config['key'], reason="requires s3 credentials")
def test_s3_store():
    pkg_store = S3Store(s3_config)

    pkg_store.create_channel("mychannel")
    pkg_store.add_file("content", "mychannel", "test.txt")
    pkg_store.add_file("content", "mychannel", "test_2.txt")

    files = pkg_store.list_files("mychannel")

    assert files == ["test.txt", "test_2.txt"]

    pkg_store.delete_file("mychannel", "test.txt")

    files = pkg_store.list_files("mychannel")
    assert files == ["test_2.txt"]
