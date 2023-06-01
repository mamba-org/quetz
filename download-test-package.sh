#!/bin/sh

mkdir -p xtensor/osx-64
mkdir -p xtensor/linux-64
mkdir -p xtensor/osx-arm64
wget https://conda.anaconda.org/conda-forge/osx-64/xtensor-0.24.3-h1b54a9f_1.tar.bz2 -P xtensor/osx-64/
wget https://conda.anaconda.org/conda-forge/linux-64/xtensor-0.24.3-h924138e_1.tar.bz2 -P xtensor/linux-64/
wget https://conda.anaconda.org/conda-forge/osx-arm64/xtensor-0.24.3-hf86a087_1.tar.bz2 -P xtensor/osx-arm64/
