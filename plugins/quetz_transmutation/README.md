# quetz_transmutation plugin

This is a plugin to use with the [quetz](https://github.com/mamba-org/quetz) package server.

## Installing

To install use:

```
pip install .
```

## Using

Run the transumtation job on all packages (server wide) using the following RESTful request:

```
QUETZ_API_KEY=...
curl -X POST localhost:8000/api/jobs \
   -H "X-api-key: ${QUETZ_API_KEY}" \
   -d '{"items_spec": "*", "manifest": "quetz-transmutation:transmutation"}'
```
