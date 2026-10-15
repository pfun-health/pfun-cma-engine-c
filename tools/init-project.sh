#!/usr/bin/env sh

set -e

# init-project.sh
# initialize tsconfig.json

npx tsc --init $@
