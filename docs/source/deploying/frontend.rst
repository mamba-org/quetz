Frontend
########

Quetz comes with a initial frontend implementation. It can be found in quetz_frontend.
To build it, one needs to install:

.. code:: bash

   mamba install 'nodejs>=14'
   cd quetz_frontend
   npm install
   npm run build
   # for development
   npm run watch

This will build the javascript files and place them in ``/quetz_frontend/dist/`` from where they are automatically picked up by the quetz server.


