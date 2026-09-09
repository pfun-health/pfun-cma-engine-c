# Building pfun-cma-engine-c

## Dependencies

- **C compiler** (GCC, Clang, or MSVC)
- **CMake** >= 3.14 (optional, alternative build)
- **Python** >= 3.11 (for Python package and Python demos)
- **uv** or pip (for Python package)

### Install uv

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## C Library

### Makefile

```sh
make                  # build shared + static library
make clean            # remove build artifacts
make debug            # debug build (-g -O0)
```

Output: `pfun_cma_engine/libpfun_cma_engine.so` and `pfun_cma_engine/libpfun_cma_engine.a`

### CMake

```sh
cmake -S . -B build/cmake-build
cmake --build build/cmake-build
```

Outputs are placed in `pfun_cma_engine/` (same as Makefile).

### Docker

```sh
docker compose run --rm build
```

This uses the Alpine-based `Dockerfile` and `compose.yaml` to configure and build
the project with CMake inside a container via `entry.sh`.

To also pre-install the Python package and demo dependencies with `uv` during
image build, enable the optional build arg:

```sh
docker compose build --build-arg ENABLE_UV_DEMO_SETUP=true build
```

## Python Package

### Install from source

```sh
uv sync --dev          # using uv (recommended)
# or
pip install -e .       # editable install via pip
```

## Demos

### Python demos

```sh
uv run python demos/python/demo.py
uv run python demos/python/demo.py --scenario morning-run
uv run python demos/python/demo.py --scenario evening-party
```

### Interactive C demo

```sh
make demo
./build/demo
```

### Tracked output snapshots

```sh
make demo-py-output
make demo-c-output
make demo-morning-run
make demo-evening-party
```

Outputs are saved under `docs/demo_outputs/`.

## Validation

```sh
uv run pytest tests/test_activity.py tests/test_demo_scenarios.py
make test
```

- `tests/test_scaling.c` is the C numerical harness used by `make test-llvm` and `make lto-test`.
- `make test` runs LLVM numerical comparison and IR structural checks.
