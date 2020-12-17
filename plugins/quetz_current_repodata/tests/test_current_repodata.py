import json
import shutil
import tempfile
from pathlib import Path


def test_current_repodata_hook(
    client,
    channel,
    subdirs,
    files,
    packages,
    config,
):
    response = client.get("/api/dummylogin/madhurt")
    assert response.status_code == 200

    pkgstore = config.get_package_store()

    old_package_filename = "test-package-0.1-0.tar.bz2"
    url = f'/api/channels/{channel.name}/files/'
    files_to_upload = {
        'files': (old_package_filename, open(old_package_filename, 'rb'))
    }
    response = client.post(url, files=files_to_upload)
    assert response.status_code == 201

    new_package_filename = "test-package-0.2-0.tar.bz2"
    url = f'/api/channels/{channel.name}/files/'
    files_to_upload = {
        'files': (new_package_filename, open(new_package_filename, 'rb'))
    }
    response = client.post(url, files=files_to_upload)
    assert response.status_code == 201

    f = pkgstore.serve_path(channel.name, "linux-64/repodata.json")
    repodata = json.load(f)
    assert len(repodata['packages']) == 2
    assert old_package_filename in repodata['packages']
    assert new_package_filename in repodata['packages']
    assert repodata['packages'][old_package_filename]['version'] == '0.1'
    assert repodata['packages'][new_package_filename]['version'] == '0.2'

    from quetz_current_repodata import main

    # this is emulating how we move repodata to the filestore now
    with tempfile.TemporaryDirectory() as tempdir:
        tempdir_path = Path(tempdir)

        f = pkgstore.serve_path(channel.name, "linux-64/repodata.json")

        stubdir = tempdir_path / channel.name / "linux-64"
        stubdir.mkdir(parents=True)

        with open(stubdir / "repodata.json", "wb") as ftemp:
            shutil.copyfileobj(f, ftemp)

        main.post_package_indexing(tempdir_path, channel.name, subdirs, files, packages)

        with open(stubdir / "current_repodata.json", "rb") as fo:
            pkgstore.add_file(fo.read(), channel.name, "linux-64/current_repodata.json")

    f = pkgstore.serve_path(channel.name, "linux-64/current_repodata.json")
    current_repodata = json.load(f)
    assert len(current_repodata['packages']) == 1
    assert old_package_filename not in current_repodata['packages']
    assert new_package_filename in current_repodata['packages']
    assert current_repodata['packages'][new_package_filename]['version'] == '0.2'
