import pluggy

hookspec = pluggy.HookspecMarker("quetz")


@hookspec
def register_router():
    """add extra endpoints to the tree"""


@hookspec
def extract_package_metadata(filehandler):
    """extract metadata from conda package"""
