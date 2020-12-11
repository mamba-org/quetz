import hashlib
import os
import shutil
import time
import uuid

import pytest

from quetz.pkgstores import LocalStore, S3Store, has_xattr

s3_config = {
    'key': os.environ.get("S3_ACCESS_KEY"),
    'secret': os.environ.get("S3_SECRET_KEY"),
    'url': os.environ.get("S3_ENDPOINT"),
    'region': os.environ.get("S3_REGION"),
    'bucket_prefix': "test",
    'bucket_suffix': "",
}

test_dir = os.path.dirname(__file__)


def test_local_store():

    temp_dir = os.path.join(test_dir, "test_pkg_store_" + str(int(time.time())))
    os.makedirs(temp_dir, exist_ok=False)

    pkg_store = LocalStore({'channels_dir': temp_dir})

    pkg_store.add_file("content", "my-channel", "test.txt")
    pkg_store.add_file("content".encode('ascii'), "my-channel", "test_2.txt")

    files = pkg_store.list_files("my-channel")

    assert files == ["test.txt", "test_2.txt"]

    pkg_store.delete_file("my-channel", "test.txt")

    files = pkg_store.list_files("my-channel")
    assert files == ["test_2.txt"]

    with pkg_store.serve_path("my-channel", "test_2.txt") as f:
        assert f.read().decode('utf-8') == "content"

    metadata = pkg_store.get_filemetadata("my-channel", "test_2.txt")

    assert metadata[0] > 0
    assert type(metadata[1]) is float

    if has_xattr:
        md5 = hashlib.md5("content".encode('ascii')).hexdigest()
        assert metadata[2] == md5
    else:
        assert type(metadata[2]) is str

    shutil.rmtree(temp_dir)


@pytest.fixture
def channel_name():
    return "mychannel" + str(uuid.uuid4())


@pytest.fixture
def s3_store(channel_name):
    pkg_store = S3Store(s3_config)
    pkg_store.create_channel(channel_name)

    yield pkg_store

    # cleanup
    files = pkg_store.list_files(channel_name)
    for f in files:
        pkg_store.delete_file(channel_name, f)
    pkg_store.fs.rmdir(pkg_store._bucket_map(channel_name))


@pytest.mark.skipif(not s3_config['key'], reason="requires s3 credentials")
def test_s3_store(s3_store, channel_name):

    pkg_store = s3_store

    pkg_store.add_file("content", channel_name, "test.txt")
    pkg_store.add_file("content", channel_name, "test_2.txt")

    files = pkg_store.list_files(channel_name)

    assert files == ["test.txt", "test_2.txt"]

    pkg_store.delete_file(channel_name, "test.txt")

    files = pkg_store.list_files(channel_name)
    assert files == ["test_2.txt"]

    metadata = pkg_store.get_filemetadata(channel_name, "test_2.txt")
    assert metadata[0] > 0
    assert type(metadata[1]) is float
    assert type(metadata[2]) is str
