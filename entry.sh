#!/usr/bin/env sh

set -eu

# entry.sh
# entrypoint for pfun-cma-engine-c container

run_build() {
	local EXTRA_ARGS="$@"
	if [ "$EXTRA_ARGS" != "" ]; then
		echo "Warning: Extra (unused) arguments were provided:\n'${EXTRA_ARGS}'"
		sleep 1s
	fi
	cmake -S . -B build/cmake-build
	cmake --build build/cmake-build
}

run_demo() {
	local SCENARIO="${1:-baseline}"
	make clean
	make
	uv sync
	uv run python demos/python/demo.py --scenario "${SCENARIO}"
}

if [ "$#" -eq 0 ]; then
	set -- "${PFUN_ENTRYPOINT_DEFAULT:-shell}"
fi

case "${1:-$PFUN_ENTRYPOINT_DEFAULT}" in
build)
	shift
	run_build "$@"
	;;
shell)
	shift
	run_demo "$@"
	;;
*)
	echo "Warning: user provided unrecognized argument(s): $@"
	;;
esac
