Configuration
=============

.. _configfile:

Config file
-----------

Most functionalities of quetz can be configured with a config file in toml format, such as this one:

.. literalinclude:: ../../../dev_config.toml


``sqlalchemy`` section
^^^^^^^^^^^^^^^^^^^^^^

Quetz can be run with SQLlite or PostgreSQL as database backends (PostgreSQL is recommended for production use). You can configure the backend by setting the URI prefixed with the backend name. To configure, PostgreSQL, you may use:

.. code::

   [sqlalchemy]
   # The URL to the database to use.
   database_url = "postgresql://postgres:mysecretpassword@localhost:5432/quetz"

   # Undocumented setting, unknown use
   database_plugin_path = ""

   # Passed directly to the "echo" argument of sqlalchemy.create_engine
   echo_sql = false

   # The pool size for sqlalchemy engine connections to postgres DBs
   # see https://docs.sqlalchemy.org/en/latest/core/pooling.html
   # Ignored for sqlite data bases
   postgres_pool_size = 10

   # The maximal number of overflow connections beyond the pool size
   # see https://docs.sqlalchemy.org/en/latest/core/pooling.html
   # Ignored for sqlite data bases
   postgres_max_overflow = 100

:database_url: URL of the database (may contain user credentials) prefixed with either ``sqlite://`` or ``postgresql://``.

:database_plugin_path: Undocumented setting, unknown use, default: `""`.

:echo_sql: Passed directly to the "echo" argument of sqlalchemy.create_engine, default: `false`.

:postgres_pool_size: The pool size for sqlalchemy engine connections to postgres DBs. See `sqlalchemy docs <https://docs.sqlalchemy.org/en/latest/core/pooling.html>`_. Ignored for sqlite data bases. Default: `10`

:postgres_max_overflow: The maximal number of overflow connections beyond the pool size. See `sqlalchemy docs <https://docs.sqlalchemy.org/en/latest/core/pooling.html>`_.  Ignored for sqlite data bases. Default: `100`

``github`` section
^^^^^^^^^^^^^^^^^^

You can use github as identity provider, i.e., users will connect to quetz with their github accounts. To register quetz as a github application, please go to the URL: `<https://github.com/settings/applications/new>`_ and add your quetz application, than copy-and-paste the provided ``client_id`` and ``client_secret`` credentials in this section.

:client_id: 
:client_secret: application credentials retrieved from github

.. note::

   Please always keep your credentials secret. Never (!) commit them to a public github repository. If this ever happens, you will need to revoke the credentials and create new ones in github web interface.

``users`` section
^^^^^^^^^^^^^^^^^

Configure default user permissions, creating default channel and super-admin permissions.

.. code::

   [users]
   # users with owner role
   admins = ["github:admin_user"]
   # users with maintainer role
   maintainers = ["google:other_user"]
   # users with memeber role
   members = ["github:some", "github:random", "github:name"]
   # default role assigned to new users
   # leave out if role should be null
   default_role = "member"
   # create a default channel for new users named {username}
   create_default_channel = false
   # wether to collect email addresses when users register
   collect_emails = false

You can use one of the following options to configure privileged users:

:admins: list of users with super-admin permissions (``owner`` role), default: empty list
:maintainers: list of users with maintainer permission (``maintainer`` role), default: empty list
:members: list of standard members (``member`` role), default: empty list

The format of the entries is ``PROVIDER:USERNAME`` where ``PROVIDER`` is the name of one of
the supported providers (such as ``google`` or ``github``).

For all other users, you can define the default role with the following option:

:default_role: default role assigned to new users, will equal to ``None`` if not specified.

Quetz can also create a channel for a newly connected user:

:create_default_channel: should a channel should be created for a user after first login, default ``false``

.. note::

   Users with role ``None`` will not be able to create channels. However, they will be able to see all public channels and can be given permissions to private channels/packages by their owners/maintainers. You can also set ``create_default_channel`` option to automatically create a channel for the user, where they will have owner permissions.

``general`` section
^^^^^^^^^^^^^^^^^^^

:redirect_http_to_https: Enforces that all incoming requests must be `https`. Any incoming requests to `http` will be redirected to the secure scheme instead. Defaults to `false`.
:package_unpack_threads: Number of parallel threads used for unpacking. Defaults to `1`.

``session`` section
^^^^^^^^^^^^^^^^^^^

Details about the session cookies that will be created in the browser.

:secret: you can create a valid secret key using the command ``openssl rand -hex 32``

``mirroring`` section
^^^^^^^^^^^^^^^^^^^^^^

You can fine tune the mirroring speed and requests made to the upstream server under ``[mirroring]``:

:batch_length: Number of packages downloaded in one batch. Defaults to `10`.
:batch_size: Maximum size to be downloaded in a batch. Defaults to `100000000` bytes.
:num_parallel_downloads: Number of parallel downloads. Defaults to `10`.


``logging`` section
^^^^^^^^^^^^^^^^^^^

You can configure Quetz logs in ``[logging]`` section:

:level: Level of logging, can be one of ``DEBUG``, ``WARNING``, ``INFO``, ``ERROR``. For more information on log levels checkout python `documentation`_.

:file: file name to save logs to (logs will be also printed out in the console), omit or set to ``None`` if you don't want to persist logs in a file.


.. _documentation: https://docs.python.org/3/howto/logging.html#when-to-use-logging

``s3`` section
^^^^^^^^^^^^^^

Quetz can store package in object cloud storage compatible with S3 interface. To configure,  use the following values:


.. note::

   To use the S3 backend you need to install the ``s3fs`` library::
      
      mamba install -c conda-forge s3fs


.. code::

    [s3]
    access_key = "AKIAIOSFODNN7EXAMPLE"
    secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    url = "https://..."
    region = ""
    bucket_prefix="..."
    bucket_suffix="..."


:access key:
:secret key: credentials to S3 account, if you use IAM roles, don't set them or set them to ``""``
:url: set to the S3 endpoint of your provider (for AWS, you can skip it)
:region: region of the S3 instance
:bucket_prefix:
:bucket_suffix: channel directories on S3 are created with the following semantics: ``{bucket_prefix}{channel_name}{bucket_suffix}``

``gcs`` section
^^^^^^^^^^^^^^^

Quetz can store packages in Google Cloud Storage. To configure, use the following values:

.. note::

    To use the GCS backend you need to install the ``gcsfs`` library::

        mamba install -c conda-forge gcsfs

.. code::

    [gcs]
    project = ".."
    token = ".."
    bucket_prefix="..."
    bucket_suffix="..."
    cache_timeout="..."
    region="..."

:project: The Google Cloud Project ID to work under
:token: A token to pass the `gcsfs`. See the `gcsfs documention <https://gcsfs.readthedocs.io/en/latest/index.html#credentials>`_ for valid values.
:bucket_prefix:
:bucket_suffix: channel buckets on GCS are created with the following semantics: ``{bucket_prefix}{channel_name}{bucket_suffix}``
:cache_timeout: Timeout in s after which local GCS cache entries are invalidated. Set to a value <=0 to disable caching completely. Default is that entries are never invalidated.
:region: Location where new buckets are created. You can find a list of available locations here: https://cloud.google.com/storage/docs/locations#available-locations.

``local_store`` section
^^^^^^^^^^^^^^^^^^^^^^^

By default, Quetz stores packages on the local filesystem and all files
are streamed by the application. To improve performances, it is recommended to deploy
Nginx in front of Quetz to serve those files.

This can be achieved by setting ``redirect_enabled`` to ``true``.
Requests for conda packages and json files will be redirected to a specific endpoint (``redirect_endpoint``)
which shall be configured in Nginx. See :ref:`nginx_config` for more information.


.. code::

    [local_store]
    redirect_enabled = true
    redirect_endpoint = "/files"


.. _worker_config:

``worker`` section
^^^^^^^^^^^^^^^^^^

Quetz can use parallel processing to speed up computation. This is achieved through invoking functions asynchronously with workers.
Different worker backends can be used. Quetz currently offers 3 types of them -- Threads, Subprocesses, and Redis-Queue workers.
Which backend to use can be configured by setting the ``type`` parameter.

If Redis-Queue is used, additional parameters such as ``redis_ip``, ``redis_port`` and ``redis_db`` need to be supplied to configure
the ``redis-server``.

.. code::

   [worker]
   type = "redis"
   redis_ip = "127.0.0.1"
   redis_port = 6379
   redis_db = 0

:type: One of the three worker backends (``thread``, ``subprocess`` or ``redis``)
:redis_ip: IP address of the redis-server.
:redis_port: The port on which the redis-server is started.
:redis_db: The database index in redis-server to connect to.

For more information, see :ref:`task_workers`.

``quotas`` section
^^^^^^^^^^^^^^^^^^

You can configure the limits (quota) on the size of uploaded packages for each channel:

:channel_quota: maximum total size (in bytes) of packages uploaded to the channel

``profiling`` section
^^^^^^^^^^^^^^^^^^^^^

Quetz provides instrumentation for profiling its endpoints.

:enable_sampling: enables sampling profiling by providing the query parameter `profile=true` (or any truth value) to the request. When active and provided the query parameter, the returned response will be highjacked to provide an HTML version of the profile output.

:interval_seconds: sampling interval in seconds. If not set, it has a default value of `0.001`.

Environment
-----------

You can also use a couple of environment variables to configure the behaviour of quetz:

=======================  ======================================  ===========================  ===================
Variable                 description                             values                       default
=======================  ======================================  ===========================  ===================
``QUETZ_LOG_LEVEL``      log level                               ERROR, INFO, WARNING, DEBUG  INFO or config file
``QUETZ_API_KEY``        api key used by quetz-client log level  string  
``QUETZ_TEST_DATABASE``  uri to the database used in tests       string                       sqlite:///:memory:
``QUETZ_TEST_DBINIT``    method to create db tabels in tests     "create-tables" or           "create-tables"
                                                                 "use-migrations" 
``S3_ACCESS_KEY``        access key to s3 (used in tests)        string                                         
``S3_SECRET_KEY``        secret key to s3 (used in tests)        string                                         
``S3_ENDPOINT``          s3 endpoint url                         string                                         
``S3_REGION``            s3 region                               string                                         
=======================  ======================================  ===========================  ===================

