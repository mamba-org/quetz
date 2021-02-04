.. _plugins_section:

Plugins
=======

Plugins can be used to extend quetz functionalities. For example, they can:

* add extra endpoints
* extract meta data from packages
* and other

Built-in plugins
----------------

Quetz repository provides a few "standard" plugins in the `plugins`_ sub-directory. However if you want to use them, you will still need to install them. After installing the Quetz server and its dependencies, go to the ``plugins`` subdirectory and install selected plugins. For example,

.. code::

   cd plugins
   pip install quetz_runexports

``quetz_runexports``
^^^^^^^^^^^^^^^^^^^^

``quetz_runexports`` plugin extract the ``run_exports`` `metadata`_ from conda packages and exposes them at the endpoint ``/api/channels/{channel_name}/packages/{package_name}/versions/{version_id}/run_exports``

.. _metadata: https://conda-forge.org/docs/maintainer/pinning_deps.html#specifying-run-exports

``quetz_repodata_patching``
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Some channels, such as ``conda-forge`` require that metadata from some packages are patched (modified) in the channel index (stored in ``repodata.json`` file and similar), so that the channel is internally consistent (i.e. all packages can be installed and dependencies satisfied). For example, a package might be too restrictive in its specification of its dependencies, so the specifications need to be relaxed in the channel index. This procedure is called repodata patching. 

``quetz_repodata_patching`` plugin implements the repodata patching. If installed, it will look for ``{channel_name}-repodata-patches`` package in the channel and apply the patch instructions in the JSON format from this package to the channel index.

For more information about the repodata patching and patch format checkout the `docs <https://docs.conda.io/projects/conda-build/en/latest/concepts/generating-index.html#repodata-patching>`_ and conda-forge `feedstock <https://github.com/conda-forge/conda-forge-repodata-patches-feedstock/tree/master/recipe>`_.

``quetz_conda_suggest``
^^^^^^^^^^^^^^^^^^^^^^^

``quetz_conda_suggest`` generates ``.map`` files specific to a particular channel and a subdir. These map files facilitate the functioning of ``conda-suggest``. More information can be seen `here <https://github.com/conda-incubator/conda-suggest>`_.
The generated map file can be accessed from the endpoint ``/api/channels/{channel_name}/{subdir}/conda-suggest``.

``quetz_current_repodata``
^^^^^^^^^^^^^^^^^^^^^^^^^^

``quetz_current_repodata`` plugin generates ``current_repodata.json`` file specific to a particular channel and a subdir. It is a trimmed version of ``repodata.json`` which contains the latest versions of each package.
More information can be accessed on the `current repodata docs <https://docs.conda.io/projects/conda-build/en/latest/concepts/generating-index.html#trimming-to-current-repodata>`_.

Creating a plugin
-----------------

Some examples can be found in `plugins`_ directory. If you want to create a new plugin, please use our `cookiecutter`_ template.

.. _plugins: https://github.com/mamba-org/quetz/tree/master/plugins
.. _cookiecutter: https://github.com/mamba-org/quetz-plugin-cookiecutter

Hooks
^^^^^

Hooks can be implemented in plugins. They are automatically called in quetz backend after or before certain operations:

.. automodule:: quetz.hooks
   :members:

