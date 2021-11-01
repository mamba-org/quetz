# quetz_harvester plugin

This is a plugin to use with the [quetz](https://github.com/mamba-org/quetz) package server that allows to extract additional metadata from the packages, using the [libcflib](https://github.com/regro/libcflib) harvester.

## Installing

To install use:

```bash
# no other libcflib deps necessary for the harvester itself
pip install git+https://git@github.com/regro/libcflib@master --no-deps
quetz plugin install plugins/quetz_harvester
```

## Using

After installing the package run the `harvest` job using the standard /jobs endpoint in quetz:

```bash
QUETZ_API_KEY=... # setup you api key retrieved through the quetz fronted
curl -X POST localhost:8000/api/jobs  -d '{"items_spec": "*", "manifest": "quetz-harvester:harvest"}' -H "X-api-key: ${QUETZ_API_KEY}"
```

it will run the `harvest` job on ALL package files on the server.

Each package will have an additional file added to the packagestore (`channel/metadata/subdir/package-name.json`).
You can access that file from the URL: `http://quetz/channels/channel/metadata/subdir/package-name.json`.
