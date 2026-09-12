#!/usr/bin/env bash

# docker-run.sh
# Runtime script for the demo

docker compose run --rm \
	-ti \
	build \
	/usr/bin/env /bin/sh -c './entry.sh shell'
