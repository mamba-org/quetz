Authenticators
==============

Quetz delegates the task of authenticating users (checking passwords etc.) to third-party
identity providers. It can communicate via the OAuth2 and OpenID protocols supported
by services such as Github and Google. This means that you can configure Quetz to have
users log in with their Github accounts. Quetz also supports the PAM-based authentication which
uses local Unix users for authentication.

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

To implement the custom authentication logic, your class should override at least
:py:meth:`~quetz.authentication.base.BaseAuthenticator.authenticate` method:

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

You can register an authenticator with an entry point.
