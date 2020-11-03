import quetz


@quetz.hookimpl
def post_package_indexing(
    pkgstore: "quetz.pkgstores.PackageStore", channel_name, subdirs
):
    for subdir in subdirs:
        fs = pkgstore.serve_path(channel_name, f"{subdir}/repodata.json")
        data = fs.read()
        pkgstore.add_file(data, channel_name, f"{subdir}/repodata_from_packages.json")
