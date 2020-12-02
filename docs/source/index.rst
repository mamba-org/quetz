.. Quetz documentation master file, created by
   sphinx-quickstart on Mon Nov  2 11:02:31 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Quetz: conda package server
===========================

The quetz project is an open source server for conda packages. It is built upon `FastAPI`_ with an API-first approach. A quetz server can have many users, channels and packages. Quetz allows for setting fine-grained permissions on channel and package-name level.

The development of quetz is taking place on `github`_.

You can also contact the community of quetz developers and users on our `gitter`_ channel.

Quetz project is supported by `QuantStack`_.

.. _github: https://github.com/mamba-org/quetz
.. _gitter: https://gitter.im/QuantStack/Lobby
.. _QuantStack: https://twitter.com/QuantStack
.. _FastAPI: https://fastapi.tiangolo.com/

Contents
--------

.. toctree::
   :maxdepth: 2

   deploying/index
   using/index
   plugins 
   qeps/index

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
