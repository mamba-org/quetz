"""
Harvests metadata out of a built conda package
"""

import io
import json
import os
import sys
import tarfile

import ruamel_yaml
from ruamel_yaml.scanner import ScannerError

METADATA_VERSION = 1


def filter_file(filename):
    if not filename:
        return False
    fn, ext = os.path.splitext(filename)
    if ext in {".txt", ".pyc"}:
        return False
    else:
        return True


# There are some meta.yaml files that were written weirdly and have some strange tag
# information in them.  This is not parsable by safe loader, so we add some more
# fallback loading
def yaml_construct_fallback(loader, node):
    return None


ruamel_yaml.add_constructor(
    "tag:yaml.org,2002:python/object/apply:builtins.getattr",
    yaml_construct_fallback,
    constructor=ruamel_yaml.SafeConstructor,
)
ruamel_yaml.add_constructor(
    "tag:yaml.org,2002:python/object:__builtin__.instancemethod",
    yaml_construct_fallback,
    constructor=ruamel_yaml.SafeConstructor,
)


def harvest(io_like):
    tf = tarfile.open(fileobj=io_like, mode="r:bz2")

    # info/files
    file_listing = tf.extractfile("info/files").readlines()
    file_listing = (fn.decode("utf8").strip() for fn in file_listing if fn)
    file_listing = [fn for fn in file_listing if filter_file(fn)]

    # info/recipe/meta.yaml
    try:
        rendered_recipe = ruamel_yaml.safe_load(tf.extractfile("info/recipe/meta.yaml"))
    except ScannerError:
        # Non parseable
        rendered_recipe = {}
    except KeyError:
        # older artifacts have a meta.yaml in another location
        try:
            rendered_recipe = ruamel_yaml.safe_load(tf.extractfile("info/meta.yaml"))
        except ScannerError:
            # Non parseable
            rendered_recipe = {}

    try:
        raw_recipe = (
            tf.extractfile("info/recipe/meta.yaml.template").read().decode("utf8")
        )
    except KeyError:
        raw_recipe = tf.extractfile("info/recipe/meta.yaml").read().decode("utf8")

    try:
        conda_build_config = ruamel_yaml.safe_load(
            tf.extractfile("info/recipe/conda_build_config.yaml")
        )
    except KeyError:
        conda_build_config = {}

    try:
        about = json.load(tf.extractfile("info/about.json"))
    except KeyError:
        about = {}
    index = json.load(tf.extractfile("info/index.json"))

    return {
        "metadata_version": METADATA_VERSION,
        "name": index["name"],
        "version": index["version"],
        "index": index,
        "about": about,
        "rendered_recipe": rendered_recipe,
        "raw_recipe": raw_recipe,
        "conda_build_config": conda_build_config,
        "files": file_listing,
    }


def harvest_from_filename(filename):
    with open(filename, "rb") as fo:
        return harvest(fo)


if __name__ == "__main__":
    o = harvest_from_filename(sys.argv[1])
    output = io.StringIO()
    ruamel_yaml.dump(o, output)
    print(output.getvalue())
