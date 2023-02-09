#!/bin/sh
curl \
  -v \
  -F 'files=@xtensor/linux-64/xtensor-0.16.1-0.tar.bz2' \
  -F 'files=@xtensor/osx-64/xtensor-0.16.1-0.tar.bz2' \
  -H 'X-API-Key: 9943a93d38ae4e4299b5dac35f82cac5' \
  http://localhost:8000/api/channels/channel0/packages/xtensor/files/
