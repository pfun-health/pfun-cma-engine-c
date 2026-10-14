# pfun-health/pfun-cma-engine-c

_Numerical engine for the [PFun CMA Model](https://github.com/pfun-health/pfun-cma-model), implemented in `C` for portability._

> [!NOTE]
> "CMA" is a fundamental initialism, short for "Cortisol-Melatonin-Adiponectin."

---

## Repository layout

- `src/` — core C model implementation
- `include/pfun_cma_engine/` — public C headers
- `pfun_cma_engine/` — Python bindings and packaged shared library, with language-surface facade dirs (`py/`, `ts/`, `c/`)
- `demos/` — interactive C demo, Python and TypeScript scenario demos, and the `scenariogen` scenario-buffer package (`demos/py/scenariogen/`)
- `docs/` — build notes and tracked demo outputs
- `tests/` — pytest and LLVM validation fixtures
- `tools/` — developer utilities

## Build and run

A Nix flake dev shell is available (`nix develop --no-pure-eval`).

See [`docs/BUILD.md`](docs/BUILD.md) for build instructions.

## Validation

```sh
$ uv run pytest \
    tests/test_activity.py \
    tests/test_demo_scenarios.py \
    tests/test_scenariogen.py \
    tests/test_scenario_db.py
$ make test
$ make precision-report
```

- Python behavior/regression coverage lives in `tests/test_activity.py`, `tests/test_demo_scenarios.py`, `tests/test_scenariogen.py`, and `tests/test_scenario_db.py`.
- LLVM numerical/structural validation is driven by `make test` and uses `tests/test_scaling.c`.
- `make test-precision` checks FP32/FP16 input/output boundary error against the FP64 C engine; `make precision-report` regenerates [`docs/PRECISION.md`](docs/PRECISION.md).

### Python scenario demos

```sh
# Run the baseline demo
$ uv run python demos/py/demo.py
# 'morning-run' scenario
$ uv run python demos/py/demo.py \
    --scenario morning-run
# 'evening-party'
$ uv run python demos/py/demo.py \
    --scenario evening-party
```

### TypeScript demo output

The TypeScript renderer calls `run_cma_model` in the compiled shared library
directly through Koffi, then formats the results as Markdown tables and ASCII
charts. It requires Node.js 22.6+ (native TypeScript type stripping), npm, and
the C shared library; it does not run the Python demo.

```sh
$ make demo-ts-output
```

To run a different scenario or point count directly:

```sh
$ make all && npm ci
$ node --experimental-strip-types demos/ts/demo.ts \
    --scenario morning-run --pts 97
```

Set `PFUN_CMA_ENGINE_LIB` to use a shared library at a non-default path.

### Interactive C demo

```sh
# Compile the C demo
$ make demo

# Run the demo binary
$ ./build/demo
```

### PFun evidentiary scenario database

Precomputed database (`SQLite`) comprising quantitative definitions of evidence-backed physiological scenarios; essentially mapping, `descriptor` → `engine-parameter` → `curated citations`.

Build and query:

```sh
# Build (precompute) the scenario database
$ uv run python demos/py/build_scenario_db.py \
    --db data/scenario_buffer.sqlite

# Query the database, return a specific scenario
$ uv run python demos/py/query_scenario_db.py \
    --db data/scenario_buffer.sqlite \
    --mood stressed --hunger starving \
    --sleep restful \
    --activity sedentary \
    --meal-schedule standard \
    --summary-only \
    --timecourse \
    --references
```

See [`docs/SCENARIO_DB.md`](docs/SCENARIO_DB.md) for the design, schema, tiers, and tests.

### Semantic scenario search (embeddings demo)

Embeds every scenario in the database (descriptor labels, physiological descriptions, glucose summary) with [`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5) via `fastembed` (ONNX; no torch needed; ~130 MB, downloaded on first run) and opens an interactive prompt. Free-text queries are matched to the best scenario by cosine similarity.

```sh
$ make demo-scenario-embeddings
query> stressed and starving after a bad night, sitting at a desk
```

Dependencies live in the optional `demo` dependency group (`uv sync --group demo`). For a single non-interactive query: `uv run --group demo python demos/py/scenario_embeddings_demo.py --query "..."`.
