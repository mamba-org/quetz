import tempfile

from quetz.pkgstores import LocalStore


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
