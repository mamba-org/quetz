.. _getting_started:

Getting started
===============

You should have `mamba <https://github.com/thesnakepit/mamba>`_ or conda installed.

Then create an environment:

.. code-block:: console

    mamba create -n quetz -c conda-forge quetz quetz-client
    conda activate quetz


Use the CLI to create a Quetz instance:

.. code-block:: console

    quetz run test_quetz --create-conf --dev --reload

Links:
 * http://localhost:8000/ - Login with your github account
 * http://localhost:8000/api/dummylogin/[ alice | bob | carol | dave] - Login with test user
 * http://localhost:8000/docs - Swagger UI for this REST service
