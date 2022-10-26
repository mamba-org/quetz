## SQL Authenticator

An authenticator that stores credentials in the Quetz SQL database using passlib. It ships with REST routets for CRUD operations on the credentials table.

### Installation

```
quetz plugin install plugins/quetz_sql_authenticator
```

### Usage

The authenticator should be active now. You can login by navigating to `<HOST>/auth/sql/login`.

### CRUD operations

The authenticator provides REST routes to create, update, and delete credentials and to reset the entire table.

`GET /api/sqlauth/credentials/`: List all users.

`GET /api/sqlauth/credentials/{username}`: Verify that a user exists.

`POST /api/sqlauth/credentials/{username}?password={password}`: Create a new user.

`PUT /api/sqlauth/credentials/{username}?password={password}`: Update a user's password.

`DELETE /api/sqlauth/credentials/{username}`: Delete a user.