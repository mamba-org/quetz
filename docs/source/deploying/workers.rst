Task Workers
=============

Quetz offers 3 types of backends for task workers. Each of them is explained below.

Thread
-----------

Thread workers process tasks in a separate thread. This functionality is in-built into FastAPI using
``BackgroundTasks`` (https://fastapi.tiangolo.com/tutorial/background-tasks/).


Subprocess
-----------

Subprocess workers start in a separate process and are implemented through ``ProcessPoolExecutor`` of the
``concurrent.futures`` module. Once again, this is shipped as a part of Quetz.


Redis
-----------

For advanced use-cases, Quetz also offers the ability to use ``redis-queue`` to manage jobs and run them on
multiple processes or even multiple servers.

To use this backend, one needs to setup ``redis`` and ``redis-queue``.

Setting up ``redis``
^^^^^^^^^^^^^^^^^^^^

Make sure that ``redis`` is installed. There are multiple ways to do this. One can compile it from source (recommended),
use a package manager for your distribution (such as ``brew`` for MacOS) and even use a Docker image.

Once ``redis`` is installed, it needs to be started. This is as simple as executing the command ``redis-server`` on a
terminal (or can be run in a container).

We also need to install ``redis-py`` (https://github.com/andymccurdy/redis-py) - the python client for Redis.

Installing ``redis-queue``
^^^^^^^^^^^^^^^^^^^^^^^^^^

``redis-queue`` is a python library that facilitates using Redis for queueing jobs and processing them in the background with
workers. The installation can be done by following instructions here: https://python-rq.org/#installation

Once this has been done, a new worker needs to be spawned (which will continuously listen for jobs to execute). This can be done by
running ``rq worker`` in a separate terminal.

Edit ``config.toml``
^^^^^^^^^^^^^^^^^^^^
Make sure to add a ``[worker]`` section with the ``type`` parameter set to ``redis``. This tells Quetz to use this backend.

.. note::

    The IP address of the machine running the ``redis-server``, along with the port and the DB Index should be
    present in the ``config.toml`` file. The default values (corresponding to running the server locally) will be picked up
    if they are not explicitly supplied.

    See :ref:`Configuration` for more details.
