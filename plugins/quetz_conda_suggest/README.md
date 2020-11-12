# quetz_conda_suggest plugin

This is a plugin to use with the [quetz](https://github.com/mamba-org/quetz) package server.

It generates `.map` files specific to a particular channel (such as `conda-forge`) and a platform (such as `linux-64`). These map files facilitate the functioning of `conda-suggest`. See https://github.com/conda-incubator/conda-suggest for additional information.

## Installing

To install use:

```
pip install .
```

## Usage

After installation, simply create channels and upload packages to them. Then, to get the `.map` file, make a GET request to the following endpoint:

`GET /api/channels/{channel_name}/{subdir}/conda-suggest`

where `{channel_name}` is the name of the channel (such as `conda-forge`) and `{subdir}` is the platform (such as `linux-64`).
