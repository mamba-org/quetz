# quetz_harvester plugin

This is a plugin to use with the [quetz](https://github.com/mamba-org/quetz) package server that allows to extract additional metadata from the packages, using the [libcflib](https://github.com/regro/libcflib) harvester.


## Installing

To install use:

```
# no other libcflib deps necessary for the harvester itself
pip install git+https://git@github.com/regro/libcflib@master --no-deps
mamba install ruamel.yaml -c conda-forge
pip install .
```


## Using

After installing the package and running a `harvest` job, each package will have an additional file added to the packagestore (`channel/metadata/subdir/package-name.json`).
You can access that file from the URL: `http://quetz/channels/channel/metadata/subdir/package-name.json`.
