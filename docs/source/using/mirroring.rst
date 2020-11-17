Mirroring
=========

Quetz can be configured to mirror existing channels from other servers.

Proxy channels
^^^^^^^^^^^^^^

A proxy channel "mirrors" another channel usually from a different server, so that the packages can be installed from the proxy as if they were installed directly from that server. All downloaded packages are cached locally and the cache is always up to date (there is no risk of serving stale packages). The reason to use the proxy channel is to limit traffic to the server of origin or to serve a channel that could be inaccessible from behind the corporate firewall.


To create a proxy channel use the properties ``mirror_channel_url=URL_TO_SOURCE_CHANNEL`` and ``mirror_mode='proxy'`` in the POST method of ``/api/channels`` endpoint. For example, to proxy the channel named ``btel`` from anaconda cloud server, you might use the following request data:

.. code:: json

   {
     "name": "proxy-channel",
     "private": false,
     "mirror_channel_url": "https://conda.anaconda.org/btel",
     "mirror_mode": "proxy"
   }

You may copy the data directly to the Swagger web interface under the heading POST ``/api/channels`` or use the cURL tool from command line. Assuming that you deployed a quetz server on port 8000 (the default) on your local machine, you could make the request with the following cURL command:


.. code:: bash

   export QUETZ_API_KEY=...
   curl -X POST "http://localhost:8000/api/channels" \
       -H  "accept: application/json" \
       -H  "Content-Type: application/json" \
       -H  "X-API-Key: ${QUETZ_API_KEY}" \
       -d '{"name":"proxy-channel",
            "private":false,
            "mirror_channel_url":"https://conda.anaconda.org/btel",
            "mirror_mode":"proxy"}'

where the value of ``QUETZ_API_KEY`` variable should be the API key that was printed when you created the quetz deployment or retrieved using the API as described in the section :ref:`generate-an-api-key`.

Then you can install packages from the channel the standard way using ``conda`` or ``mamba``:

.. code:: bash

   mamba install --strict-channel-priority -c http://localhost:8000/channels/proxy-channel nrnpython

Mirror channels
^^^^^^^^^^^^^^^

A mirror channel is an exact copy of another channel usually from a different (anaconda or quetz) server. The packages are downloaded from that server and added to the mirror channel. The mirror channel supports the standard Quetz API except requests that would add or modify the packages (POST ``/api/channels/{name}/files``, for example). Mirror channels can be used to off load traffic from the primary server, or to create a channel clone on the company Intranet.

Creating a mirror channel is similar to creating proxy channels except that you need to change the value of ``mirror_mode`` attribute from ``proxy`` to ``mirror`` (and choose a more suitable channel name obviously):

.. code:: json

   {
     "name": "mirror-channel",
     "private": false,
     "mirror_channel_url": "https://conda.anaconda.org/btel",
     "mirror_mode": "mirror"
   }



.. code:: bash

   export QUETZ_API_KEY=...
   curl -X POST "http://localhost:8000/api/channels" \
       -H  "accept: application/json" \
       -H  "Content-Type: application/json" \
       -H  "X-API-Key: ${QUETZ_API_KEY}" \
       -d '{"name":"mirror-channel",
            "private":false,
            "mirror_channel_url":"https://conda.anaconda.org/btel",
            "mirror_mode":"mirror"}'

Mirror channels are read only (you can not add or change packages in these channels), but otherwise they are fully functional Quetz channels and support all standard read (GET) operations. For example, you may list all packages using GET ``/api/channels/{channel_name}/packages`` endpoint:

.. code:: bash

   curl http://localhost:8000/api/channels/mirror-channel/packages

Synchronising mirror channel
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If packages are added or modified on the primary server from which they were pulled initially, they won't be updated automatically in the mirror channel. However, you can trigger such synchronisation manually using the PUT ``/api/channels/{channel_name}/actions`` endpoint:


.. code:: bash

   curl -X PUT localhost:8000/api/channels/mirror-channel/actions \ 
       -H "X-API-Key: ${QUETZ_API_KEY}" \
       -d '{"action": "synchronize"}'

Only channel owners or maintainers are allowed to trigger synchronisation, therefore you have to provide a valid API key of a privileged user.
