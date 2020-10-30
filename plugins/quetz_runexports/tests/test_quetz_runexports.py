import shutil
import tempfile
from contextlib import contextmanager
from unittest import mock

from quetz_runexports import db_models

from quetz.condainfo import CondaInfo

pytest_plugins = "quetz.testing.fixtures"


def test_run_exports_endpoint(
    client, channel, package, package_version, package_runexports, db, session_maker
):
    version_id = f"{package_version.version}-{package_version.build_string}"

    response = client.get(
        f"/api/channels/{channel.name}/packages/{package.name}/versions/{version_id}/run_exports"  # noqa
    )
    assert response.status_code == 200
    assert response.json() == {"weak": ["somepackage > 3.0"]}


def test_endpoint_without_metadata(
    client, channel, package, package_version, db, session_maker
):
    version_id = f"{package_version.version}-{package_version.build_string}"

    response = client.get(
        f"/api/channels/{channel.name}/packages/{package.name}/versions/{version_id}/run_exports"  # noqa
    )
    assert response.status_code == 404


def test_post_add_package_version(package_version, config, db, session_maker):
    filename = "test-package-0.1-0.tar.bz2"

    with tempfile.SpooledTemporaryFile(mode='wb') as target:
        with open(filename, 'rb') as fid:
            shutil.copyfileobj(fid, target)
        target.seek(0)
        condainfo = CondaInfo(target, filename)

    @contextmanager
    def get_db():
        yield db

    from quetz_runexports import main

    with mock.patch("quetz_runexports.main.get_db", get_db):
        main.post_add_package_version(package_version, condainfo)

    meta = db.query(db_models.PackageVersionMetadata).first()

    assert meta.data == '{}'

    # modify runexport and re-save
    condainfo.run_exports = {"weak": ["somepackage < 0.3"]}
    with mock.patch("quetz_runexports.main.get_db", get_db):
        main.post_add_package_version(package_version, condainfo)

    meta = db.query(db_models.PackageVersionMetadata).all()

    assert len(meta) == 1

    assert meta[0].data == '{"weak": ["somepackage < 0.3"]}'
