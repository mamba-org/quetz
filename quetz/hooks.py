import pluggy

hookspec = pluggy.HookspecMarker("quetz")

@hookspec
def register_router():
    """add extra endpoints to the tree"""
