# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import bz2
import gzip
import hashlib
import time
from datetime import datetime, timezone


def add_static_file(contents, channel_name, subdir, fname, pkgstore, file_index=None):
    raw_file = contents.encode("utf-8")
    bz2_file = bz2.compress(raw_file)
    gzp_file = gzip.compress(raw_file)

    path = f"{subdir}/{fname}" if subdir else fname
    pkgstore.add_file(bz2_file, channel_name, f"{path}.bz2")
    pkgstore.add_file(gzp_file, channel_name, f"{path}.gz")
    pkgstore.add_file(raw_file, channel_name, f"{path}")

    if file_index:
        add_entry_for_index(file_index, subdir, fname, raw_file)
        add_entry_for_index(file_index, subdir, f"{fname}.bz2", bz2_file)
        add_entry_for_index(file_index, subdir, f"{fname}.gz", gzp_file)


def add_entry_for_index(files, subdir, fname, data_bytes):
    md5 = hashlib.md5()
    sha = hashlib.sha256()

    md5.update(data_bytes)
    sha.update(data_bytes)

    files[subdir].append(
        {
            "name": fname,
            "size": len(data_bytes),
            "timestamp": datetime.now(timezone.utc),
            "md5": md5.hexdigest(),
            "sha256": sha.hexdigest(),
        }
    )


class TicToc:
    def __init__(self, description):
        self.description = description

    def __enter__(self):
        self.start = time.time()

    def __exit__(self, ty, val, tb):
        self.stop = time.time()
        print(f"[TOC] {self.description}: {self.stop - self.start}")

    @property
    def elapsed(self):
        return self.stop - self.start
