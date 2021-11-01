## DictionaryAuthenticator

This is a **demo** of creating new authenticator classes.

NOT MEANT FOR USE IN PRODUCTION!

Sample authenticator inspired by an example from [JupyterHub docs.](https://jupyterhub.readthedocs.io/en/stable/reference/authenticators.html#authenticator-authenticate-method).

### Installation

```bash
quetz plugin install plugins/quetz_dictauthenticator
```

### Configure

add the following section to your `config.toml`:

```ini
[dictauthenticator]
users = ["happyuser:happy", "unhappyuser:unhappy"]
```

where users is a list of pairs of username and passwords (in plain text, sic!) separated by colon `:`.

### Usage

The authenticator should be active now, you can login by going to the URL `http://HOST/auth/dict/login`
