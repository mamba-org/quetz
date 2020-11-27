# quetz_repodata_zchunk plugin

This is a plugin to use with the [quetz](https://github.com/mamba-org/quetz) package server that allows to serve/download the repodata using [zchunk](https://github.com/zchunk/zchunk), so that not all the repodata is downloaded every time it changes, but only the changed parts. This dramatically reduces the download time, and is more scalable in the long run (as repodata grows with time).


## Installing

To install use:

```
pip install .
mamba install zchunk -c conda-forge
```


## Using

After installing the package, the `repodata.json` from any channel will also be available in the zchunk format, and if you have a recent enough version of `mamba`, the repodata will be downloaded using `zckdl` (the zchunk download utility), providing all the benefits described above.
