#!/usr/bin/env sh

# docker-build.sh
# Build pfun-cma-model-engine-c (shared libs, optionally with python-based demo)

docker compose build \
       --build-arg ENABLE_UV_DEMO_SETUP=true \
       build
