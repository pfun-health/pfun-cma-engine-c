# Building pfun-cma-engine-c

Instructions for building the C library, Python package, and running demos.

---

## Dependencies

- **C compiler** (GCC, Clang, or MSVC)
- **CMake** >= 3.14 (optional, alternative build)
- **Python** >= 3.11 (for Python package and Python demos)
- **uv** or pip (for Python package)
- **DuckDB** >= 1.5 Python package (scenario buffer; installed via `uv sync --dev`)

### Nix / devenv (optional)

A `flake.nix` provides a reproducible shell (Python 3.11, uv, gcc, make, pkg-config).
It syncs the uv environment on entry.

```sh
nix develop --no-pure-eval   # or: echo 'use flake . --impure' > .envrc && direnv allow
```

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

---

## Python Package

### Install from source

```sh
uv sync --dev          # using uv (recommended)
# or
pip install -e .       # editable install via pip
```

---

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

### Scenario database buffer

```sh
# full buffer (768 scenarios x 193 points) -> data/scenario_buffer.sqlite
.venv/bin/python demos/python/build_scenario_db.py --db data/scenario_buffer.sqlite

# small core buffer (15 scenarios x 97 points) for fast tests/CI
.venv/bin/python demos/python/build_scenario_db.py --db /tmp/scenario_core.sqlite --tier core

# query a scenario: exact + nearest match, summary, timecourse, references
.venv/bin/python demos/python/query_scenario_db.py --db data/scenario_buffer.sqlite \
  --mood stressed --hunger starving --sleep restful --activity sedentary --meal-schedule standard \
  --summary-only --timecourse --references
```

Design, schema, tiers, and physiology: [`docs/SCENARIO_DB.md`](SCENARIO_DB.md).

### Embedding-based scenario search

```sh
make demo-scenario-embeddings   # builds the DB if needed, then starts an interactive query prompt
```

Uses `BAAI/bge-small-en-v1.5` (fastembed/ONNX, cosine similarity; queries get the BGE retrieval instruction prefix). Requires the `demo` dependency group (installed automatically by `uv run --group demo`) and network access on first run to download the model.

---

## Validation

```sh
uv run pytest tests/test_activity.py tests/test_demo_scenarios.py \
  tests/test_scenariogen.py tests/test_scenario_db.py
make test
make test-precision
make precision-report
```

- `tests/test_scaling.c` is the C numerical harness used by `make test-llvm` and `make lto-test`.
- `make test` runs LLVM numerical comparison and IR structural checks.
- `make test-precision` checks numeric input/output boundary quantization; `make precision-report` regenerates the measured results in [`PRECISION.md`](PRECISION.md).
