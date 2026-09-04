# Building pfun-cma-engine-c

## Dependencies

- **C compiler** (GCC, Clang, or MSVC)
- **CMake** >= 3.14 (optional, alternative build)
- **Python** >= 3.11 (for Python package)
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
the project with CMake inside a container.

## Python Package

### Install from source

```sh
uv sync --dev          # using uv (recommended)
# or
pip install -e .       # editable install via pip
```

### Run demo

```sh
uv run ipython -i -- ./demo.py
```
