Configuration
=============

Config file
-----------

Most functionalities of quetz can be configured with a config file in toml format, such as this one:

.. literalinclude:: ../../dev_config.toml


``sqlalchemy`` section
^^^^^^^^^^^^^^^^^^^^^^

Quetz can be run with SQLlite or PostgreSQL as database backends (PostgreSQL is recommended for production use). You can configure the backend by setting the URI prefixed with the backend name. To configure, PostgreSQL, you may use:

.. code::

   [sqlalchemy]
   database_url = "postgresql://postgres:mysecretpassword@localhost:5432/quetz"

:database_url: URL of the database (may contain user credentials) prefixed with either ``sqlite://`` or ``postgresql://``.

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
   admins = ["admin_user"]
   # users with maintainer role
   maintainers = ["other_user"]
   # users with memeber role
   members = ["some", "random", "name"]
   # default role assigned to new users
   # leave out if role should be null
   default_role = "member"
   # create a default channel for new users named {username}
   create_default_channel = false

You can use one of the following options to configure privilaged users:

:admins: list of users with super-admin permissions (``owner`` role), default: empty list
:maintainers: list of users with maintainer permission (``maintainer`` role), default: empty list
:members: list of standard members (``member`` role), default: empty list

For all other users, you can define the default role with the following option:

:default_role: default role assigned to new users, will equal to ``None`` if not specified.

Quetz can also create a channel for a newly connected user:

:create_default_channel: should a channel should be created for a user after first login, default ``false``

.. note::

   Users with role ``None`` will not be able to create channels. However, they will be able to see all public channels and can be given permissions to private channels/packages by their owners/maintainers. You can also set ``create_default_channel`` option to automatically create a channel for the user, where they will have owner permissions.


``session`` section
^^^^^^^^^^^^^^^^^^^

Details about the session cookies that will be created in the browser.

:secret: you can create a valid secret key using the command ``openssl rand -hex 32``

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

Environment
-----------

You can also use a couple of environment variables to configure the behaviour of quetz:

====================  ======================================  ===========================  ===================
Variable              description                             values                       default
====================  ======================================  ===========================  ===================
``QUETZ_LOG_LEVEL``   log level                               ERROR, INFO, WARNING, DEBUG  INFO or config file
``QUETZ_API_KEY``     api key used by quetz-client log level  string  
====================  ======================================  ===========================  ===================

