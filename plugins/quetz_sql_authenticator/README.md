## SQL Authenticator

An authenticator that stores credentials in the Quetz SQL database using passlib. Ships with CLI tools for CRUD operations on the credentials table.

### Dependencies

This plugin depends on `passlib`.

### Installation

```
quetz plugin install plugins/quetz_sql_authenticator
```

### Usage

The authenticator should be active now. You can login by navigating to `<HOST>/auth/sql/login`.

### CLI Tool

The authenticator provides a CLI tool to create, update, and delete credentials and to reset the entire table.

#### Dependencies

The CLI tools has `click` as an additional dependency.

#### Usage

You need to set the `QUETZ_CONFIG_FILE` environment variable to the path of your Quetz configuration file, e.g. `/home/user/quetz_server/config.toml`. Otherwise, the CLI tool will not be able to find the database.

If the Database URL specified in the configuration file is a relative path to a
SQLite database, you need to make sure to run the CLI from the directory
that that path is relative to.

Please check `quetz-sql-authenticator --help` for more details.
