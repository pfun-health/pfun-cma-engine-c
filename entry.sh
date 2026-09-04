#!/bin/sh

set -eu

run_build() {
  cmake -S . -B build/cmake-build
  cmake --build build/cmake-build
}

if [ "$#" -eq 0 ]; then
  set -- "${PFUN_ENTRYPOINT_DEFAULT:-shell}"
fi

case "$1" in
  build)
    shift
    run_build "$@"
    ;;
  shell)
    shift
    if [ "$#" -eq 0 ]; then
      exec sh
    fi
    exec "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
