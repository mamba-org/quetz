Basics
######


Channels
^^^^^^^^

Create a channel
""""""""""""""""

First, make sure you're logged in to the web app.

Then, using the swagger docs at ``<deployment url>:<port>/docs``, POST to ``/api/channels`` with the name and description of your new channel:

.. code:: json

   {
     "name": "my-channel",
     "description": "Description for my-channel",
     "private": false
   }

This will create a new channel called ``my-channel`` and your user will be the Owner of that channel.

API keys
^^^^^^^^

.. _generate-an-api-key:

Generate an API key
"""""""""""""""""""

API keys are scoped per channel, per user and optionally per package.
In order to generate an API key the following must be true:

1. First, make sure you're logged in to the web app.
2. The user must be part of the target channel (you might need to create a channel first, see the previous section on how to create a channel via the swagger docs)
3. Go to the swagger docs at ``<deployment url>:<port>/docs`` and POST to ``/api/api-keys``:

.. code:: json

   {
     "description": "my-test-token",
     "roles": [
       {
         "role": "owner",
         "channel": "my-channel"
       }
     ]
   }

4. Then, GET on ``/api/api-keys`` to retrieve your token
5. Finally, set this value to QUETZ_API_KEY so you can use quetz-client to interact with the server.


