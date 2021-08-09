.. _nginx_config:

Nginx
=====

Nginx can be deployed in front of Quetz to improve performances when using local storage.

.. note::

   When using ``S3`` or ``Azure`` as file storage, packages are served directly from the cloud.
   Using Nginx won't make much difference in that case.


Configuration
-------------

Here is an example configuration to use Nginx in front of Quetz:

.. code::

   worker_processes  1;
   pid        /tmp/nginx.pid;

   events {
      worker_connections  1024;
   }

   http {

      map $cache $control {
         1       "max-age=1200";
      }
      map $uri $cache {
         ~*\.(json)$    1;
      }

      proxy_temp_path /tmp/proxy_temp;
      client_body_temp_path /tmp/client_temp;
      fastcgi_temp_path /tmp/fastcgi_temp;
      uwsgi_temp_path /tmp/uwsgi_temp;
      scgi_temp_path /tmp/scgi_temp;

      include       mime.types;
      default_type  application/octet-stream;

      sendfile        on;
      tcp_nopush      on;
      tcp_nodelay     on;

      keepalive_timeout  65;

      gzip  on;
      gzip_types  application/json;

      client_max_body_size 100m;

      upstream quetz {
         server 127.0.0.1:8000;
      }

      server {
         listen      8080;
         add_header  Cache-Control $control;

         server_name  localhost;

         location / {
           proxy_set_header Host $http_host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection $connection_upgrade;
           proxy_redirect off;
           proxy_buffering off;
           proxy_pass http://quetz;
         }

         location /files/channels/ {
           # path for channels
           alias /quetz-deployment/channels/;

           secure_link $arg_md5,$arg_expires;
           secure_link_md5 "$secure_link_expires$file_name mysecrettoken";

           if ($secure_link = "") { return 403; }
           if ($secure_link = "0") { return 410; }
         }
      }

      map $http_upgrade $connection_upgrade {
         default upgrade;
         '' close;
      }
   }

Requests for files under ``/files/channels/`` will be served by Nginx. Note the
optional secure_link and secure_link_md5 configuration. This enables expiring,
authenticated links. To use these links (important with private channels) you
will need to set the same secret in the quetz config

.. code::

   [local_store]
   redirect_enabled = true
   redirect_endpoint = "/files"
   redirect_secret = "mysecrettoken"  # this has to correspond with nginx config!
   redirect_expiration = 3600  # expire link after 3600 seconds (1 hour)

All other requests are passed to the Quetz application, which is running locally on port 8000
in this example.

.. warning::

   This configuration disables any authentication to access files under the ``channels``
   directory. This isn't an issue if you only have public channels.
   Authentication for private channels hasn't been implemented yet.

client_max_body_size
^^^^^^^^^^^^^^^^^^^^

The default maximum allowed size of the client request body is 1MB.
Don't forget to increase it to upload bigger packages.
Request Entity Too Large (413) will be returned otherwise.

.. code::

   client_max_body_size 100m;

Compress json files
^^^^^^^^^^^^^^^^^^^

Nginx can be configured to automatically compress json files using::

    gzip  on;
    gzip_types  application/json;

Add cache-control header for json files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It's possible to add cache-control header for json files.
For the ``repodata.json`` file to be cached by conda, ``max-age`` can be added
to the header by Nginx when serving json files.

Under the ``http`` section::

   map $cache $control {
     1       "max-age=1200";
   }
   map $uri $cache {
     ~*\.(json)$    1;
   }

Under the ``server`` section::

   add_header  Cache-Control $control;

Note that the same value will be used for all channels.
