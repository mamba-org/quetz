# quetz_tos plugin

This is a plugin to use with the [quetz](https://github.com/mamba-org/quetz) package server.

It checks if a user has signed terms of services document or not. An `owner` need not sign the TOS.
However, `maintainer` or `members` need to sign terms of services to make sure they have the relevant access
to their resources. In case of not signing, their permissions will be restricted -- for eg: they might not be able to upload a package to a channel even if their status permits them to.

## Installing

To install use:

```
pip install .
```

## Usage

- `GET /api/tos` endpoint is used to get information about latest terms of service document
- `POST /api/tos/sign` endpoint is used to sign a particular (or latest) terms of service document
- `POST /api/tos/upload` endpoint is used to upload a terms of service document. Only `owners` can do it.
