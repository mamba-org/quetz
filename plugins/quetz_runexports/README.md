# quetz_runexports

Quetz plugin to extract and expose `run_exports` from package files. 

## Installation

Install quetz and then from this plugin directory do:

```
pip install -e .
```

The plugin should be automatically integrated with quetz server, when you start it.


## Usage

To retrieve the `run_exports` make a GET requests on the following endpoint:

`GET /api/channels/{channel_name}/packages/{package_name}/versions/{version_id}/run_exports`

where `{version_id}` is the version number and the build hash with the minus sign in between (`version_number-build_hash`). For example:

```
# download zeromq package
curl -OL https://anaconda.org/conda-forge/zeromq/4.3.3/download/linux-64/zeromq-4.3.3-he1b5a44_2.tar.bz2

# export an api key
export QUETZ_API_KEY=...

# create a new channel
curl -X POST http://localhost:8000/api/channels -d '{"name": "test-channel", "private": false}' -H "X-API-Key: ${QUETZ_API_KEY}"

# upload a package
quetz-client http://localhost:8000/api/channels/test-channel zeromq-4.3.3-he1b5a44_2.tar.bz2

# get run_exports
curl -X GET http://localhost:8000/api/channels/test-channel/packages/zeromq/versions/4.3.3-he1b5a44_2/run_exports
```

This should return:

```
{"weak":["zeromq >=4.3.3,<4.4.0a0"]}
```
