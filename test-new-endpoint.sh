#!/bin/sh
curl \
  -v \
  -X POST \
  -T '21cmfast/linux-64/21cmfast-3.0.2-py36h1af98f8_1.tar.bz2' \
  -H 'X-API-Key: dc49786370e843d4a8a9b44226a1d114' \
  http://localhost:8000/api/channels/channel0/upload/21cmfast-3.0.2-py36h1af98f8_1.tar.bz2?sha256=1154fceeb5c4ee9bb97d245713ac21eb1910237c724d2b7103747215663273c2

# -F 'files=@xtensor/osx-64/xtensor-0.16.1-0.tar.bz2' \
