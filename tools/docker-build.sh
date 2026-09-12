#!/usr/bin/env bash

set -e

# docker-build.sh
# Build pfun-cma-model-engine-c (shared libs, optionally with python-based demo)

make clean && \
    rm -rf ./.venv && \
    docker compose build \
	   --quiet \
	   --build-arg ENABLE_UV_DEMO_SETUP=true \
	   build
