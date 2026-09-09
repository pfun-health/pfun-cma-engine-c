# pfun-health/pfun-cma-engine-c

_Optimized C extensions for the PFun CMA model (numerical engine)._

## Repository layout

- `src/` — core C model implementation
- `pfun_cma_engine/` — Python bindings and packaged shared library
- `demos/` — interactive C demo plus Python scenario demos
- `docs/` — build notes and tracked demo outputs
- `tests/` — pytest and LLVM validation fixtures
- `tools/` — developer utilities

## Build and run

See [`docs/BUILD.md`](docs/BUILD.md) for build instructions.

### Python scenario demos

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
