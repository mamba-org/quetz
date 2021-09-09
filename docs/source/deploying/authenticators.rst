Authenticators
==============

Quetz delegates the task of authenticating users (checking passwords etc.) to third-party
identity providers. It can communicate via the OAuth2 and OpenID protocols supported
by services such as Github and Google. This means that you can configure Quetz to have
users log in with their Github accounts. Quetz also supports the PAM-based authentication which
uses local Unix users for authentication.

.. warning::
    While it is possible to register and use multiple authenticators at once, it is heavily discouraged
    and a warning will be printed. Currently quetz does not automatically merge accounts based on email
    addresses and usernames from different auth providers can overlap.

    A warning will be printed when running quetz with multiple activated auth providers.

Built-in authenticators
-----------------------

These authenticator classes are built-in and can be activated by adding relevant
section to the configuration file. See below for more details (the class names
are only for reference, they are already included in the Quetz server).

PAM
^^^

.. autoclass:: quetz.authentication.pam.PAMAuthenticator

Github
^^^^^^

.. autoclass:: quetz.authentication.github.GithubAuthenticator

Gitlab
^^^^^^

.. autoclass:: quetz.authentication.gitlab.GitlabAuthenticator


Google
^^^^^^

.. autoclass:: quetz.authentication.google.GoogleAuthenticator


Jupyterhub
^^^^^^^^^^

.. autoclass:: quetz.authentication.jupyterhub.JupyterhubAuthenticator



Custom authenticators
---------------------

You can also implement new authenticators for Quetz server.


Authentication base classes
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The authenticator should derive from one of the base classes:

.. autoclass:: quetz.authentication.base.BaseAuthenticator

.. autoclass:: quetz.authentication.base.SimpleAuthenticator

.. autoclass:: quetz.authentication.oauth2.OAuthAuthenticator

Implement authentication logic
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To implement some custom authentication logic, your class should override at least
:py:meth:`~quetz.authentication.base.BaseAuthenticator.authenticate` method (except
for :py:class:`~quetz.authentication.oauth2.OAuthAuthenticator` subclasses):

.. automethod:: quetz.authentication.base.BaseAuthenticator.authenticate

For example, the custom authenticator might be:

.. code:: python

  class DictionaryAuthenticator(SimpleAuthenticator):
      """Simple demo authenticator that authenticates with
      users from a dictionary of usernames and passwords."""
      
      passwords: dict = {"happyuser": "happy"}
      provider = "dict"
  
      async def authenticate(self, request, data, **kwargs):
          """``data`` argument is username and password entered by 
          user in the login form."""

          if self.passwords.get(data['username']) == data['password']:
              return data['username']


Registering authenticator
^^^^^^^^^^^^^^^^^^^^^^^^^

The standard way to register an authenticator with Quetz, is to distibute it as a plugin
(see :ref:`plugins_section`). 
To automatize the creation of a plugin, check out our cookiecutter `template`_.

.. _template: https://github.com/mamba-org/quetz-plugin-cookiecutter

If not using the cookiecutter, you can register an authenticator with Quetz by defining 
an entry point.  You can create entry point with the following snippet in the ``setup.py``:

.. code::

    from setuptools import setup
    
    # you will need to adapt these variables
    # to the names from your package
    PACKAGE_NAME = quetz_dictauthenticator
    AUTHENTICATOR_CLASS = "DictAuthenticator"
    MODULE_NAME = authenticators

    setup(
        name="quetz-dictauthenticator",
        install_requires="quetz",
        entry_points={
            "quetz.authenticator": [
                f"{AUTHENTICATOR_CLASS.lower()} = {PACKAGE_NAME}:{MODULE_NAME}.{AUTHENTICATOR_CLASS}"
            ]
        },
        packages=[PACKAGE_NAME],
    )
