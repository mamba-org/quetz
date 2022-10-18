## SQL Authenticator

An authenticator that stores credentials in the Quetz SQL database using passlib. Ships with CLI tools for CRUD operations on the credentials table.

### Dependencies

This plugin depends on `passlib`.

### Installation

```
pip install -e .
```

### Usage

The authenticator should be active now. You can login by navigating to `<HOST>/auth/sql/login`.

### CLI Tool

The authenticator provides a CLI tool to create, update, and delete credentials and to reset the entire table.

#### Dependencies

The CLI tools has `click` as an additional dependency.

#### Usage

Please check `quetz-sql-authenticator --help` for more details.
