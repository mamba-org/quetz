import bz2
import gzip
import json
from pathlib import Path

import pytest
import zstandard

from quetz import channel_data
from quetz.config import CompressionConfig
from quetz.tasks.indexing import update_indexes


@pytest.fixture
def empty_channeldata(dao):
    return channel_data.export(dao, "")


def expected_compressed_files(files, bz2_enabled, gz_enabled, zst_enabled):
    args = locals().copy()
    return [
        f"{s}.{suffix}"
        for s in files
        for suffix in ["bz2", "gz", "zst"]
        if s.endswith(".json") and args[f"{suffix}_enabled"]
    ]


@pytest.mark.parametrize("bz2_enabled", [True, False])
@pytest.mark.parametrize("gz_enabled", [True, False])
@pytest.mark.parametrize("zst_enabled", [True, False])
def test_update_indexes_empty_channel(
    config, public_channel, dao, empty_channeldata, bz2_enabled, gz_enabled, zst_enabled
):
    pkgstore = config.get_package_store()

    update_indexes(
        dao,
        pkgstore,
        public_channel.name,
        compression=CompressionConfig(bz2_enabled, gz_enabled, zst_enabled),
    )

    files = pkgstore.list_files(public_channel.name)

    base_files = [
        "channeldata.json",
        "index.html",
        "noarch/index.html",
        "noarch/repodata.json",
    ]
    expected_files = base_files.copy()
    expected_files.extend(
        expected_compressed_files(base_files, bz2_enabled, gz_enabled, zst_enabled)
    )

    assert sorted(files) == sorted(expected_files)

    channel_dir = Path(pkgstore.channels_dir) / public_channel.name
    with open(channel_dir / "channeldata.json", "r") as fd:
        assert json.load(fd) == empty_channeldata


@pytest.mark.parametrize("bz2_enabled", [True, False])
@pytest.mark.parametrize("gz_enabled", [True, False])
@pytest.mark.parametrize("zst_enabled", [True, False])
def test_update_indexes_empty_package(
    config,
    public_channel,
    public_package,
    dao,
    empty_channeldata,
    bz2_enabled,
    gz_enabled,
    zst_enabled,
):
    pkgstore = config.get_package_store()

    update_indexes(
        dao,
        pkgstore,
        public_channel.name,
        compression=CompressionConfig(bz2_enabled, gz_enabled, zst_enabled),
    )

    files = pkgstore.list_files(public_channel.name)

    base_files = [
        "channeldata.json",
        "index.html",
        "noarch/index.html",
        "noarch/repodata.json",
    ]

    expected_files = base_files.copy()
    expected_files.extend(
        expected_compressed_files(base_files, bz2_enabled, gz_enabled, zst_enabled)
    )

    assert sorted(files) == sorted(expected_files)

    channel_dir = Path(pkgstore.channels_dir) / public_channel.name
    with open(channel_dir / "channeldata.json", "r") as fd:
        channeldata = json.load(fd)

    assert public_package.name in channeldata["packages"].keys()

    assert channeldata["packages"].pop(public_package.name) == {}
    assert channeldata == empty_channeldata


@pytest.mark.parametrize("bz2_enabled", [True, False])
@pytest.mark.parametrize("gz_enabled", [True, False])
@pytest.mark.parametrize("zst_enabled", [True, False])
def test_update_indexes_with_package_version(
    config,
    public_channel,
    public_package,
    package_version,
    dao,
    bz2_enabled,
    gz_enabled,
    zst_enabled,
):
    args = locals().copy()
    pkgstore = config.get_package_store()

    update_indexes(
        dao,
        pkgstore,
        public_channel.name,
        compression=CompressionConfig(bz2_enabled, gz_enabled, zst_enabled),
    )

    files = pkgstore.list_files(public_channel.name)

    base_files = [
        "channeldata.json",
        "index.html",
        "linux-64/index.html",
        "linux-64/repodata.json",
        "noarch/index.html",
        "noarch/repodata.json",
    ]

    expected_files = base_files.copy()
    expected_files.extend(
        expected_compressed_files(base_files, bz2_enabled, gz_enabled, zst_enabled)
    )
    expected_files.append(f"linux-64/{package_version.filename}")

    assert sorted(files) == sorted(expected_files)

    channel_dir = Path(pkgstore.channels_dir) / public_channel.name
    with open(channel_dir / "channeldata.json", "r") as fd:
        channeldata = json.load(fd)

    assert public_package.name in channeldata["packages"].keys()

    # Check compressed repodata identical to repodata.json when enabled
    # or that it doesn't exist when disabled
    extensions = ("bz2", "gz", "zst")
    enabled_compression_extensions = [
        ext for ext in extensions if args[f"{ext}_enabled"]
    ]
    disabled_compression_extensions = set(extensions) - set(
        enabled_compression_extensions
    )
    for subdir in ("noarch", "linux-64"):
        repodata_json_path = channel_dir / subdir / "repodata.json"
        with open(repodata_json_path, "r") as fd:
            ref_repodata = json.load(fd)
        for extension in enabled_compression_extensions:
            with open(f"{repodata_json_path}.{extension}", "rb") as fd:
                compressed_data = fd.read()
            if extension == "bz2":
                data = bz2.decompress(compressed_data)
            elif extension == "gz":
                data = gzip.decompress(compressed_data)
            else:
                data = zstandard.ZstdDecompressor().decompress(compressed_data)
            repodata = json.loads(data)
            assert repodata == ref_repodata
        for extension in disabled_compression_extensions:
            assert not Path(f"{repodata_json_path}.{extension}").exists()
