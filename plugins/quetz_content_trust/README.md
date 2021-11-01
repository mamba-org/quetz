# quetz_content_trust plugin

This is a plugin to use with the [quetz](https://github.com/mamba-org/quetz) package server.

It generates signed repodata files for different `subdirs` of a particular `channel`.
However, this is only done when a `private key` for that particular `channel` exists in the database.
See `usage` section below for more details.

## Installing

To install use:

```bash
quetz plugin install plugins/quetz_content_trust
```

## Usage

- `POST /api/content-trust/upload-root` endpoint is used to upload `root.json` files.
- `POST /api/content-trust/upload-key-mgr` endpoint is used to upload `key_mgr.json` files.
- `POST /api/content-trust/private-key` endpoint is used to add a `private key` for a particular `channel` in the database. The endpoint expects a JSON with two fields: `{channel: abc, private_key: xyz}`
