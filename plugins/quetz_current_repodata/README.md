# quetz_current_repodata plugin

This is a plugin to use with the [quetz](https://github.com/mamba-org/quetz) package server.

It generates `current_repodata.json` file specific to a particular channel (such as `conda-forge`) and a platform (such as `linux-64`). It is a trimmed version of `repodata.json` which contains the latest versions of each package. For more information, refer https://docs.conda.io/projects/conda-build/en/latest/concepts/generating-index.html#trimming-to-current-repodata

## Installing

To install use:

```bash
quetz plugin install plugins/quetz_current_repodata
```
