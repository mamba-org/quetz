# quetz_mamba_solve plugin

This is a plugin to use with the [quetz](https://github.com/mamba-org/quetz) package server.

It takes `a list of channels`, a `subdir` (also known as `platform`) and a `spec` as input and generates a specification file (similar to what `conda list --explicit` would produce). The contents of this file can be used to create an identical environment on a machine with the same platform. This can be done using the command `conda create --name myenv --file spec-file.txt` where `spec-file.txt` is the file containing the response from this API endpoint.

## Installing

Make sure that both quetz and mamba are installed in the current environment. (It doesn't suffice to have the mamba executable installed in the base environment; the API must be available from Python.)

```bash
mamba install mamba
```

To install this plugin:

```bash
pip install .
```
