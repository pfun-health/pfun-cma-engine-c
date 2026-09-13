# pfun-health/pfun-cma-engine-c

_Numerical engine for the [PFun CMA Model](https://github.com/pfun-health/pfun-cma-model), implemented in `C` for portability._

> [!NOTE]
> "CMA" is a fundamental initialism, short for "Cortisol-Melatonin-Adiponectin."

---

## Repository layout

- `src/` — core C model implementation
- `pfun_cma_engine/` — Python bindings and packaged shared library
- `demos/` — interactive C demo plus Python scenario demos and the `scenariogen` scenario-buffer package (`demos/python/scenariogen/`)
- `docs/` — build notes and tracked demo outputs
- `tests/` — pytest and LLVM validation fixtures
- `tools/` — developer utilities

## Build and run

See [`docs/BUILD.md`](docs/BUILD.md) for build instructions.

## Validation

```sh
$ uv run pytest \
    tests/test_activity.py \
    tests/test_demo_scenarios.py \
    tests/test_scenariogen.py \
    tests/test_scenario_db.py
$ make test
```

- Python behavior/regression coverage lives in `tests/test_activity.py`, `tests/test_demo_scenarios.py`, `tests/test_scenariogen.py`, and `tests/test_scenario_db.py`.
- LLVM numerical/structural validation is driven by `make test` and uses `tests/test_scaling.c`.

### Python scenario demos

```sh
# Run the baseline demo
$ uv run python demos/python/demo.py
# 'morning-run' scenario
$ uv run python demos/python/demo.py \
    --scenario morning-run
# 'evening-party'
$ uv run python demos/python/demo.py \
    --scenario evening-party
```

### Interactive C demo

```sh
# Compile the C demo
$ make demo

# Run the demo binary
$ ./build/demo
```

### PFun evidentiary scenario database

Precomputed database (`DuckDB`) comprising quantitative definitions of evidence-backed physiological scenarios; essentially mapping, `descriptor` → `engine-parameter` → `curated citations`.

Build and query:

```sh
# Build (precompute) the scenario database
$ uv run python demos/python/build_scenario_db.py \
    --db data/scenario_buffer.duckdb

# Query the database, return a specific scenario
$ uv run python demos/python/query_scenario_db.py \
    --db data/scenario_buffer.duckdb \
    --mood stressed --hunger starving \
    --sleep restful \
    --activity sedentary \
    --meal-schedule standard \
    --summary-only \
    --timecourse \
    --references
```

See [`docs/SCENARIO_DB.md`](docs/SCENARIO_DB.md) for the design, schema, tiers, and tests.
