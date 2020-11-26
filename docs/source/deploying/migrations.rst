Migrations
==========

When the data classes in Quetz are modified (for example, a column is added, remove or updated), the database need to be upgraded while keeping the stored data. This cane be done automatically, using migrations. Quetz uses `alembic`_ to handle migrations.

.. note::

   Before running any of the commands below, you need to make sure that your database is backed up. The backup process depends on the infrastrcuture, but in the simplest case it may involve the dump of the whole database (using ``pg_dump`` for example).

Migrating database
------------------

When you install a new version of Quetz or Quetz plugin, you should apply the provided migrations using the ``quetz init-db`` command. For example, assuming that your deployment is in ``deployment_dir`` folder:

.. code::

   quetz init-db deployment_dir


.. _alembic : https://alembic.sqlalchemy.org


Adding new migrations
---------------------

Once you modified your data models in Quetz, you can autogenerate the appropriate migrations using ``make-migrations`` command:

.. code::

   quetz init-db deployment_dir # to make sure that the db is up-to-date
   quetz make-migrations deployment_dir --message "my revision message"

This should create a new file in ``quetz/migrations/versions`` directory, which you can then add to the git repository. Then you can apply the migrations the standard way:

.. code::

   quetz init-db deployment_dir # to make sure that the db is up-to-date

.. note::

   For running unit test there is no need to create the migrations, the testing framework
   will create all tables automatically for you. However, if you want to run the tests 
   with the migrations, you can configure it with env variable: :code:`QUETZ_TEST_DBINIT=use-migrations pytest quetz`

Initializing migrations for plugins
-----------------------------------

To use migrations in plugins, you need to initialize them. Our cookiecutter template will create the necessary backbone for you, you will just need to define your models in the ``db_models.py`` file of plugin directory, and then run the command:

.. code::

   quetz make-migrations deployment_dir --message "initial revision" --initialize --plugin quetz-plugin_name 

This should create a new migration script in `PLUGIN_DIR/migrations/versions`.

.. note::

   If you want to add the migration script to you working directory, you need to install the plugin using the development mode: ``pip install -e PATH_TO_PLUGIN``

As always the ``quetz init-db`` will upgrade automatically your database to reflect the data models defined in the plugin.

Adding migrations for plugins
-----------------------------

When you change the data model in the plugin, you can create the required migrations using the same ``quetz make-migrations`` command, but without ``--initialize``:

.. code::

   quetz make-migrations deployment_dir --message "second revision"  --plugin quetz-plugin_name 
