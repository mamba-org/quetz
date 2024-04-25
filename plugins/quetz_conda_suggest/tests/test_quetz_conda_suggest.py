import io
import shutil
import tarfile
import tempfile
from contextlib import contextmanager
from unittest import mock

import pytest
from quetz_conda_suggest import db_models

from quetz.condainfo import CondaInfo


def test_conda_suggest_endpoint_without_upload(client, channel, subdir):
    response = client.get(f"/api/channels/{channel.name}/{subdir}/conda-suggest")  # noqa
    assert response.status_code == 200
    assert response.content == b"null"
    assert response.json() == None  # noqa: E711


def test_post_add_package_version(package_version, db, config):
    filename = "test-package-0.1-0.tar.bz2"

    with tempfile.SpooledTemporaryFile(mode="wb") as target:
        with open(filename, "rb") as fid:
            shutil.copyfileobj(fid, target)
        target.seek(0)
        condainfo = CondaInfo(target, filename)

    @contextmanager
    def get_db():
        yield db

    from quetz_conda_suggest import main

    with mock.patch("quetz_conda_suggest.main.get_db_manager", get_db):
        main.post_add_package_version(package_version, condainfo)

    meta = db.query(db_models.CondaSuggestMetadata).first()

    assert meta.data == "{}"

    # modify `files` and re-save
    condainfo.files = [
        b"bin/test-bin\n",
        b"include/tpkg.h\n",
        b"include/tpkg_utils.h\n",
        b"lib/cmake/test-package/tpkgConfig.cmake\n",
        b"lib/cmake/test-package/tpkgConfigVersion.cmake\n",
        b"lib/libtpkg.so\n",
        b"lib/pkgconfig/libtpkg.pc\n",
    ]
    with mock.patch("quetz_conda_suggest.main.get_db_manager", get_db):
        main.post_add_package_version(package_version, condainfo)

    meta = db.query(db_models.CondaSuggestMetadata).all()

    assert len(meta) == 1
    assert meta[0].data == '{"test-bin": "test-package"}'


@pytest.fixture
def plugins():
    return ["quetz-conda_suggest"]


def test_conda_suggest_endpoint_with_upload(
    client,
    db,
    channel,
    package,
    subdir,
    config,
    profile,
):
    response = client.get("/api/dummylogin/madhurt")
    filename = "test-package-0.1-0.tar.bz2"

    @contextmanager
    def get_db():
        yield db

    # extract existing data
    tar = tarfile.open(name=filename, mode="r:bz2")
    existing_files = tar.getmembers()
    existing_files_data = {}
    for each_file in existing_files:
        each_file_extracted = tar.extractfile(each_file)
        if each_file_extracted is None:
            raise RuntimeError(each_file)
        each_file_data = each_file_extracted.read()
        existing_files_data[each_file] = each_file_data
    tar.close()

    # write content in `info/files`
    files_data = [
        "bin/test-bin\n",
        "include/tpkg.h\n",
        "include/tpkg_utils.h\n",
        "lib/cmake/test-package/tpkgConfig.cmake\n",
        "lib/cmake/test-package/tpkgConfigVersion.cmake\n",
        "lib/libtpkg.so\n",
        "lib/pkgconfig/libtpkg.pc\n",
    ]
    files_content = "".join(files_data)
    b = files_content.encode("utf-8").strip()
    t = tarfile.TarInfo("info/files")
    t.size = len(b)

    # re-create archive with updated `info/files`
    tar = tarfile.open(name=filename, mode="w:bz2")
    for each_file, each_file_data in existing_files_data.items():
        tar.addfile(each_file, io.BytesIO(each_file_data))
    tar.addfile(t, io.BytesIO(b))
    tar.close()

    with mock.patch("quetz_conda_suggest.main.get_db_manager", get_db):
        url = f"/api/channels/{channel.name}/files/"
        files = {"files": (filename, open(filename, "rb"))}
        response = client.post(url, files=files)

        assert response.status_code == 201

    response = client.get(f"/api/channels/{channel.name}/{subdir}/conda-suggest")  # noqa

    assert response.status_code == 200
    assert response.headers["content-length"] == "22"
    assert response.content == b"test-bin:test-package\n"
