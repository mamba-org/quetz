# Quetz Content Trust

## Testing

Few scripts are provided to perform a manual integration test of package signing.

This is intended to be used by channels owners/maintainers to get familiar with the workflow of generating TUF roles (delegations, etc.) and push them on a Quetz server.

For that, simply run the 2 following commands from your quetz source directory:
- `quetz run test_quetz --copy-conf ./dev_config.toml --dev --reload --delete` to get an up and running server
- `python plugins/quetz_content_trust/docs/test_script.py` to generate TUF roles, push them on the server but also push an empty `test-package` package

then just test from client side: `micromamba create -n foo -c http://127.0.0.1:8000/get/channel0 test-package --no-rc -y -vvv --repodata-ttl=0 --experimental --verify-artifacts`

You can also simulate invalid signatures/role metadata running:
- `python plugins/quetz_content_trust/docs/test_corrupted_key_mgr_metadata.py`: overwrite `KeyMgr` role metadata with an invalid delegation
- `python plugins/quetz_content_trust/docs/test_corrupted_key_mgr_sigs.py`: overwrite `KeyMgr` role keys with an invalid one
