## SQL Authenticator

An authenticator that stores credentials as sha256-hashed values in a SQL database. Ships with CLI tools for CRUD operations on the credentials table.

### Dependencies

This plugin has `sqlmodel` and `passlib` as an additional dependencies.
Also, you might need certain database drivers, like `psycopg2`, depending on what SQL backend you use.

### Installation

```
pip install -e .
```

### Infrastructure

The authenticator expects to connect to a SQL database with a `credentials` table in the following format.

```py
from sqlmodel import Field, SQLModel

class Credentials(SQLModel, table=True):
    """Table for storing username and password, sha-256 hashed."""
    username: str = Field(primary_key=True)
    password: str
```

### Configure

Add the following section to your `config.toml`:

```toml
[sql_authenticator]
database_url = "SQLALCHEMY_URL"
```

Where `SQLALCHEMY_URL` is a [SQLAlchemy URL](https://docs.sqlalchemy.org/en/14/core/engines.html), pointing to your database.

### Usage

The authenticator should be active now. You can login by navigating to `<HOST>/auth/sql/login`.

### CLI Tool

The authenticator provides a CLI tool to create, update, and delete credentials and to reset the entire table.

#### Dependencies

The CLI tools has `click` as an additional dependency.

#### Usage

Please check `quetz-sql-authenticator --help` for more details.
