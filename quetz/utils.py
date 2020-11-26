# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import hashlib
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
