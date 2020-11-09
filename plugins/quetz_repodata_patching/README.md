# quetz_repodata_patching plugin

A plugin for [quetz](https://github.com/mamba-org/quetz) package server that implements the repodata patching. Repodata patching allow for hotfixing package index by changing some metadata in ``repodata.json`` files on the fly. For more information, see [conda-build](https://docs.conda.io/projects/conda-build/en/latest/concepts/generating-index.html#repodata-patching) docs.


## Installing

To install use:

```
pip install .
```

## Using

After installing the package, the `repodata.json` from any channel will be patched with the files found in the `{channel_name}-repodata-patches` package in the same channel. This package should contain one `patch_instructions.json` file per subdir (for example, `linux-64/patch_instructions.json`). For details, follow the structure of the [package](https://anaconda.org/conda-forge/conda-forge-repodata-patches) from `conda-forge` channel or checkout the scripts to generate it in the conda-forge [feedstock](https://github.com/conda-forge/conda-forge-repodata-patches-feedstock/tree/master/recipe).
