Plugins
=======

Plugins can be used to extend quetz functionalities. For example, they can:

* add extra endpoints
* extract meta data from packages
* and other

Some examples can be found in `plugins`_ directory. If you want to add a new plugin, please use our `cookiecutter`_ template.

.. _plugins: https://github.com/mamba-org/quetz/tree/master/plugins
.. _cookiecutter: https://github.com/mamba-org/quetz-plugin-cookiecutter

Hooks
-----

Hooks can be implemented in plugins. They are automatically called in quetz backend after or before certain operations:

.. automodule:: quetz.hooks
   :members:

