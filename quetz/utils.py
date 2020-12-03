# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import hashlib
import time
from datetime import datetime, timezone


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
