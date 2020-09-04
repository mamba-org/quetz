# Copyright 2020 Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import fnmatch
import hashlib
import json
import tarfile
import time
from io import BytesIO
from zipfile import ZipFile

import zstandard

from quetz import db_models

INFO_BOOLEAN_FIELDS = (
    "activate.d",
    "deactivate.d",
    "post_link",
    "pre_link",
    "pre_unlink",
    "binary_prefix",
    "text_prefix",
)
INFO_OPTIONAL_FIELDS = ("version",)
ABOUT_OPTIONAL_FIELDS = (
    "description",
    "dev_url",
    "doc_source_url",
    "doc_url",
    "home",
    "icon_hash",
    "icon_url",
    "license",
    "recipe_origin",
    "source_git_url",
    "source_url",
    "summary",
)
ABOUT_MAP_FIELDS = ("keywords", "identifiers", "tags")

MAX_CONDA_TIMESTAMP = 253402300799


class CondaInfo:
    def __init__(self, file, filename):
        self.channeldata = {}
        self.package_format = None
        self.info = {}
        self.about = {}
        self.paths = {}
        self.run_exports = {}
        self._parse_conda(file, filename)

    def _map_channeldata(self):
        channeldata = {}
        channeldata["packagename"] = self.info["name"]
        timestamp = int(self.info.get("timestamp", time.time()))
        if timestamp > MAX_CONDA_TIMESTAMP:
            # Convert timestamp from milliseconds to seconds
            timestamp //= 1000
        channeldata["timestamp"] = timestamp
        channeldata["subdirs"] = [self.info["subdir"]]

        for field in INFO_BOOLEAN_FIELDS:
            channeldata[field] = False

        for field in ABOUT_OPTIONAL_FIELDS:
            if field in self.about:
                channeldata[field] = self.about[field]
            else:
                channeldata[field] = None

        for field in INFO_OPTIONAL_FIELDS:
            if field in self.info:
                channeldata[field] = self.info[field]
            else:
                channeldata[field] = None

        for field in ABOUT_MAP_FIELDS:
            if (field in self.about) and (len(self.about[field]) > 0):
                channeldata[field] = self.about[field]
            else:
                channeldata[field] = None

        for path in self.paths["paths"]:
            pathname = path["_path"]
            if "/etc/conda/deactivate.d/" in pathname:
                channeldata["deactivate.d"] = True
            elif "etc/conda/activate.d/" in pathname:
                channeldata["activate.d"] = True
            if "file_mode" in path:
                if path["file_mode"] == "binary":
                    channeldata["binary_prefix"] = True
                elif path["file_mode"] == "text":
                    channeldata["text_prefix"] = True
            for linkname in ("pre-link", "post-link", "pre-unlink"):
                if fnmatch.fnmatch(pathname, f"*/.*-{linkname}.*"):
                    channeldata[linkname.replace("-", "_")] = True

        channeldata["run_exports"] = self.run_exports

        self.channeldata = channeldata

    def _load_jsons(self, tar):
        self.info = json.load(tar.extractfile("info/index.json"))
        self.about = json.load(tar.extractfile("info/about.json"))
        self.paths = json.load(tar.extractfile("info/paths.json"))
        try:
            exports_file = tar.extractfile("info/run_exports.json")
        except KeyError:
            self.run_exports = {}
        else:
            self.run_exports = json.load(exports_file)

        self._map_channeldata()

    def _calculate_file_hashes(self, file):
        BLOCK_SIZE = 1024 * 1024  # 1MiB
        md5 = hashlib.md5()
        sha = hashlib.sha256()
        file.seek(0)
        size = 0
        while True:
            b = file.read(BLOCK_SIZE)
            if len(b) > 0:
                size += len(b)
                md5.update(b)
                sha.update(b)
            else:
                break
        self.info["size"] = size
        self.info["md5"] = md5.hexdigest()
        self.info["sha256"] = sha.hexdigest()

    def _parse_conda(self, file, filename):
        filehandle = file._file
        if filename.endswith(".conda"):
            self.package_format = db_models.PackageFormatEnum.conda
            with ZipFile(filehandle) as zf:
                infotars = [_ for _ in zf.namelist() if _.startswith("info-")]
                infotar = infotars[0]
                with zf.open(infotar) as zfobj:
                    if infotar.endswith(".zst"):
                        zstd = zstandard.ZstdDecompressor()
                        # zstandard.stream_reader cannot seek backwards
                        # and tarfile.extractfile() seeks backwards
                        fobj = BytesIO(zstd.stream_reader(zfobj).read())
                    else:
                        fobj = zfobj
                    with tarfile.open(fileobj=fobj, mode="r") as tar:
                        self._load_jsons(tar)
        else:
            self.package_format = db_models.PackageFormatEnum.tarbz2
            with tarfile.open(fileobj=filehandle, mode="r:bz2") as tar:
                self._load_jsons(tar)

        self._calculate_file_hashes(file)

        self.info = dict(sorted(self.info.items(), key=lambda item: item[0]))
