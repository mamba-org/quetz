# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.
try:
    import pluggy

    hookimpl = pluggy.HookimplMarker("quetz")
except ImportError:
    pass
