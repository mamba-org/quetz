import pluggy

hookspec = pluggy.HookspecMarker("quetz")


@hookspec
def register_router():
    """add extra endpoints to the tree"""


@hookspec
def post_add_package_version(version, condainfo):
    """hook for post-processsing after adding a package version"""
