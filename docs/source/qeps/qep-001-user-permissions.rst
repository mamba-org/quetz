QEP 1: quetz permission design
------------------------------

Problem
^^^^^^^

* there is currently no option to set user permissions at server level
* all users that log with their github account can create channels and upload packages, which might be not desired especially if the server is visible on the public network

Use cases
^^^^^^^^^

* allow or forbid users to create channels
* allow or forbid users to mirror channels
* superuser role - user that can modify all channels or modify user permissions

Proposal
^^^^^^^^

Add role to user model: each user should have one of the roles: ``owner``, ``maintainer``, ``member``. By default new users should have no role assigned (role = null). server ``maintainer`` or ``owner`` can add a role of ``member`` for a user, that would allow them to create new channels (except mirror channels).

Role permissions:

* empty
 
  - can read their user data

* ``member``

  - can create normal channels

* ``maintainer`` (admin)

  - all above and
  - can assign ``member`` role to users
  - can read all users' data
  - can create mirror and proxy channels
  - has access to all channels (including all private channels)

* ``owner`` (super-admin)

  - all above and
  - can assign ``maintainer`` role to users

The role can be modified by the PUT method to the endpoint `/api/users/{username}/role` with the following data:

.. code::

   {
     "role": "ROLE"
   }

The role can be retrieved by the GET request to the same endpoint.

Roles can be configure with a config file:

.. code:: toml

   [users]
   # users with owner role
   admins = ["wolfv"]
   # users with maintainer role
   maintainers = ["btel"]
   # users with memeber role
   members = ["some", "random", "name"]
   # default role assigned to new users
   # leave out if role should be null
   default_role = "member" 
   # create a default channel for new users named {username}
   create_default_channel = false

API key
"""""""

A user can create a server-wide API key with the same permissions as user, by the POST request to `/api/api-keys` endpoint, with the following data:


.. code::

   {
     "description": "key description, does not have to be unique"
     "roles": []
   }

Note that the roles list should remain empty. Adding channel or package roles to `roles` will **downgrade** the permissions of the key.

Implementation
^^^^^^^^^^^^^^

Add a new ``role`` column to the User model in the database that can have one of 4 values ``owner``, ``maintainer``, ``member`` or ``null`` (actual null object, not the string).

Discussion
^^^^^^^^^^

* the names of server roles, even though not optimal, were chosen such that they are the same as channel and package roles
* this proposal does not allow user to have multiple roles, because the roles create hierarchical relationship i.e., ``owner`` > ``maintainer`` > ``member``
