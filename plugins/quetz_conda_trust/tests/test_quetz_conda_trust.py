import json
import shutil
import tempfile
from pathlib import Path


def test_post_index_signed_repodata(
    client, config, channel, reposigning_private_key
):
    response = client.get("/api/dummylogin/madhurt")
    assert response.status_code == 200

    pkgstore = config.get_package_store()

    filename = "test-package-0.1-0.tar.bz2"
    url = f'/api/channels/{channel.name}/files/'
    files_to_upload = {'files': (filename, open(filename, 'rb'))}
    response = client.post(url, files=files_to_upload)
    assert response.status_code == 201

    from quetz_conda_trust import main

    with tempfile.TemporaryDirectory() as tempdir:
        tempdir_path = Path(tempdir)

        f = pkgstore.serve_path(channel.name, "linux-64/repodata.json")

        stubdir = tempdir_path / channel.name / "linux-64"
        stubdir.mkdir(parents=True)

        with open(stubdir / "repodata.json", "wb") as ftemp:
            shutil.copyfileobj(f, ftemp)

        main.post_package_indexing(
            tempdir_path, channel.name, ['linux-64'], {'linux-64': []}, {'linux-64': []}
        )

        with open(stubdir / "repodata_signed.json", "rb") as fo:
            pkgstore.add_file(fo.read(), channel.name, "linux-64/repodata_signed.json")

    f = pkgstore.serve_path(channel.name, "linux-64/repodata_signed.json")
    signed_repodata = json.load(f)

    signature_key = "f46b5a7caa43640744186564c098955147daa8bac4443887bc64d8bfee3d3569"
    assert "signatures" in signed_repodata
    assert filename in signed_repodata["signatures"]
    assert signature_key in signed_repodata["signatures"][filename]
    assert "signature" in signed_repodata["signatures"][filename][signature_key]
    assert (
        len(signed_repodata["signatures"][filename][signature_key]["signature"]) == 128
    )
