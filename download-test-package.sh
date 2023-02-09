#!/bin/sh

mkdir -p xtensor/osx-64
mkdir -p xtensor/linux-64
wget https://conda.anaconda.org/conda-forge/osx-64/xtensor-0.16.1-0.tar.bz2 -P xtensor/osx-64/
wget https://conda.anaconda.org/conda-forge/linux-64/xtensor-0.16.1-0.tar.bz2 -P xtensor/linux-64/
