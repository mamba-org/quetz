#!/bin/sh
curl \
  -v \
  -F 'files=@xtensor/linux-64/xtensor-0.16.1-0.tar.bz2' \
  -F 'files=@xtensor/osx-64/xtensor-0.16.1-0.tar.bz2' \
  -H 'X-API-Key: E_KaBFstCKI9hTdPM7DQq56GglRHf2HW7tQtq6si370' \
  http://localhost:8000/channels/channel0/packages/xtensor/files/
