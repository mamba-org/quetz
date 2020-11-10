import shutil
import tempfile
from contextlib import contextmanager
from unittest import mock

from quetz_conda_suggest import db_models

from quetz.condainfo import CondaInfo


def test_conda_suggest_endpoint_without_upload(client, channel, subdir):
    response = client.get(
        f"/api/channels/{channel.name}/{subdir}/conda-suggest"
    )  # noqa
    assert response.status_code == 404
    assert response.json() == {
        'detail': 'conda-suggest map file for test_channel.linux-64 not found'
    }


def test_post_add_package_version(package_version, db, config):
    filename = "test-package-0.1-0.tar.bz2"

    with tempfile.SpooledTemporaryFile(mode='wb') as target:
        with open(filename, 'rb') as fid:
            shutil.copyfileobj(fid, target)
        target.seek(0)
        condainfo = CondaInfo(target, filename)

    @contextmanager
    def get_db():
        yield db

    from quetz_conda_suggest import main

    with mock.patch("quetz_conda_suggest.main.get_db", get_db):
        main.post_add_package_version(package_version, condainfo)

    meta = db.query(db_models.CondaSuggestMetadata).first()

    assert meta.data == '{}'

    # modify `files` and re-save
    condainfo.files = [
        b'bin/test-bin\n',
        b'include/tpkg.h\n',
        b'include/tpkg_utils.h\n',
        b'lib/cmake/test-package/tpkgConfig.cmake\n',
        b'lib/cmake/test-package/tpkgConfigVersion.cmake\n',
        b'lib/libtpkg.so\n',
        b'lib/pkgconfig/libtpkg.pc\n',
    ]
    with mock.patch("quetz_conda_suggest.main.get_db", get_db):
        main.post_add_package_version(package_version, condainfo)

    meta = db.query(db_models.CondaSuggestMetadata).all()

    assert len(meta) == 1
    assert meta[0].data == '{"test-bin": "test-package"}'


def test_conda_suggest_endpoint_with_upload(client, channel, package, subdir, config):
    response = client.get("/api/dummylogin/madhurt")

    filename = "test-package-0.1-0.tar.bz2"
    url = f'/api/channels/{channel.name}/files/'
    files = {'files': (filename, open(filename, 'rb'))}
    response = client.post(url, files=files)

    assert response.status_code == 201

    response = client.get(
        f"/api/channels/{channel.name}/{subdir}/conda-suggest"
    )  # noqa
    print(response.status_code)
