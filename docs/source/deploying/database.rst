Database
========


PostgreSQL
^^^^^^^^^^

By default, quetz will run with sqlite database, which works well for local tests and small local instances. However, if you plan to run quetz in production, we recommend to configure it with the PostgreSQL database. There are several options to install PostgreSQL server on your local machine or production server, one of them being the official PostgreSQL docker image. 


Running PostgreSQL server with docker
"""""""""""""""""""""""""""""""""""""

You can the PostgresSQL image from the docker hub and start the server with the commands:

.. code::

   docker pull postgres
   docker run --name some-postgres -p 5432:5432 -e POSTGRES_PASSWORD=mysecretpassword -d postgres

This will start the server with the user ``postgres`` and the password ``mysecretpassword`` that will be listening for connection on the port 5432 of localhost.

You can then create a database in PostgreSQL for quetz tables:

.. code::

   sudo -u postgres psql -h localhost -c 'CREATE DATABASE quetz OWNER postgres;'

Deploying Quetz with PostgreSQL backend
"""""""""""""""""""""""""""""""""""""""

Then in your configuration file (such as `dev_config.toml`) replace the `[sqlalchemy]` section with:

.. code::

   [sqlalchemy]
   database_url = "postgresql://postgres:mysecretpassword@localhost:5432/quetz"

Finally, you can create and run a new quetz deployment based on this configuration (we assume that you saved it in file `config_postgres.toml`):


.. code::

   quetz run postgres_quetz --copy-conf config_postgres.toml 

Note that this recipe will create an ephemeral PostgreSQL database and it will delete all data after the `some-postgres` container is stopped and removed. To make the data persistent, please check the documentation of the `postgres` [image](https://hub.docker.com/_/postgres/)  or your container orchestration system (Kubernetes or similar).

Running tests with PostgreSQL backend
"""""""""""""""""""""""""""""""""""""

To run the tests with the PostgreSQL database instead of the default SQLite, follow the steps [above](#running-postgresql-server-with-docker) to start the PG server. Then create an new database:

.. code::

   psql -U postgres -h localhost -c 'CREATE DATABASE test_quetz OWNER postgres;'

You will be asked to type the password to the DB, which you defined when starting your PG server. In the docker-based instructions above, we set it to `mysecretpassword`.

To run the tests with this database you need to configure the `QUETZ_TEST_DATABASE` environment variable:

.. code::

   QUETZ_TEST_DATABASE="postgresql://postgres:mysecretpassword@localhost:5432/test_quetz" pytest -v ./quetz/tests


