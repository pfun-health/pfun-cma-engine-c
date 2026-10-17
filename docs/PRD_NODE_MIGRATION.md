# PRD: Migrate All Python-Based Build Targets to Node.js / TypeScript

**Status:** Proposed
**Owner:** pfun-health
**Scope:** Every `make` target, script, test, container, and dev-environment
definition that currently requires Python or `uv`.

---

## 1. Summary

Today a clean checkout needs Python 3.11 and `uv` to run the demos, scenario
database, precision checks, CGM data fetch, LLVM conversion, benchmarks and the
test suite. The TypeScript demo (`demos/ts/demo.ts`, Koffi + Node 22.6+ with
`--experimental-strip-types`) already proves the C engine can be driven from
Node without Python.

**Goal:** after this work, `python`, `uv`, `pip`, `numpy`, `pytest`, `pandas`,
`matplotlib`, `llvmlite`, `fastembed` and a `.venv` are **not required** by any
`make` target, Docker stage, Nix shell or documented workflow. The toolchain is
C compiler + (optional) LLVM/emscripten/GSL + Node.js + npm.

## 2. Goals / Non-Goals

### Goals
- G1. Every Python-backed Make target has a Node/TS equivalent with the same
  target name, flags, and output format.
- G2. Numerical results are equivalent to the Python implementation within
  documented tolerances (see §7).
- G3. Remove `uv`/Python from `Makefile`, `Dockerfile`, `entry.sh`,
  `flake.nix`, docs and tracked packaging files.
- G4. Single dependency manager: `npm` (`package.json` + `package-lock.json`).

### Non-Goals
- Changing the C engine (`src/`, `include/`) or its ABI.
- Changing model semantics, scenario definitions, or scenario DB contents.
- Publishing a Python wheel (see §9 – this is a deliberate removal, needs
  sign-off).
- Replacing the C/Nuklear demo, WASM demo, or GSL CGM fit (already Python-free).

## 3. Current State Inventory

Python-dependent build targets and files:

| Area | Make target / entry | Python source | Third-party deps |
|---|---|---|---|
| Python env | `python-setup`, `python-setup-dev`, `python-clean-venv` | `pyproject.toml`, `uv.lock`, `.python-version` | uv |
| Package build | `setup.py` (ctypes ext build) | `setup.py`, `MANIFEST.in` | setuptools |
| Engine wrapper | (used by demos/tests) | `pfun_cma_engine/pfun_cma_engine.py` | numpy, ctypes |
| JIT engines | benchmarks only | `pfun_cma_engine/jit_engine.py`, `orc_jit_engine.py`, `demos/py/demo_jit.py` | llvmlite, numpy |
| Demo | `demo-py-output`, `demo-morning-run`, `demo-evening-party`, `outputs` | `demos/py/demo.py`, `scenarios.py` | numpy, pandas?, tabulate, matplotlib |
| Scenario DB | `scenario-db`, `scenario-db-core`, `query-demo` | `demos/py/build_scenario_db.py`, `query_scenario_db.py`, `scenariogen/{db,descriptors,mapping,references,zotero}.py` | sqlite3, numpy |
| Embeddings | `demo-scenario-embeddings`, `demo-time2eat` | `scenario_embeddings_demo.py`, `time2eat.py` | fastembed/ONNX (BGE-small) |
| Tests | `test`, `test-scenariogen`, `test-precision` | `tests/test_*.py` | pytest |
| Precision | `precision-report` | `tools/precision_report.py` | numpy |
| CGM data | `fetch-cgm` | `tools/fetch_cgm_data.py` | urllib, csv, hashlib |
| LLVM | `llvm-ir`, `llvm-verify`, `lto-test`, `test-llvm`, `analyze-*` | `tools/convert-to-llvm.py` (invoked as `python3` in Makefile) | none (subprocess to clang) |
| Benchmarks | (manual) | `tools/benchmark-compare.py` | numpy, llvmlite |
| Containers/Env | `Dockerfile` (`ENABLE_UV_DEMO_SETUP`), `entry.sh` `shell` (`uv run python demos/py/demo.py`), `flake.nix` (python311, uv, `.venv`) | — | — |
| Misc | `docs/BUILD.md`, `README.md`, `flake.nix` http server (`python3 -m http.server`) | — | — |

Already Python-free (no change except dependency hygiene): `libs`, `all`,
`demo`, `demo-c-output`, `demo-ts-output`, `demo-wasm`, `cgm-*`, `test-cgm`,
`check-ir`, `format`.

## 4. Target Architecture

```
src/*.c ──► libpfun_cma_engine.so ──► Koffi ──► ts/ library ──► demos, tools, tests
```

- **TypeScript library** `pfun_cma_engine/ts/` (currently README-only): typed
  Koffi binding for `run_cma_model` and parameter structs, returning
  `Float64Array` series. Mirrors `pfun_cma_engine/pfun_cma_engine.py`
  (`run_cma_engine_c`) including parameter defaults, activity parameters and
  `MAX_POINTS` validation. Single shared module imported by every TS tool; the
  existing inline binding in `demos/ts/demo.ts` is refactored onto it.
- **Layout:** `demos/ts/`, `tools/*.ts`, `tests/*.test.ts`,
  `demos/ts/scenariogen/` (port of `scenariogen`). Python dirs are deleted, not
  left alongside.
- **Runtime:** Node.js ≥ 22.6 (type stripping; use `.ts` import extensions and
  erasable-syntax-only TS). Pin via `engines` in `package.json` and `.nvmrc`.
  `tsc --noEmit` is used for type checking only (not a build step).
- **Test runner:** built-in `node:test` + `node:assert` (no new dependency).
- **Numeric arrays:** `Float64Array` plus small local helpers; no numpy-like
  dependency.

## 5. Functional Requirements

### FR-1 Engine binding (replaces `pfun_cma_engine.py`)
- Load `pfun_cma_engine/libpfun_cma_engine.so` (path overridable by
  `PFUN_CMA_LIB`); error clearly if not built (`run make libs`).
- Expose `runCmaEngine(params, opts)` with the same inputs/outputs as
  `run_cma_engine_c`.
- Support FP64 plus FP32/FP16 boundary quantization helpers
  (`Math.fround`; software half-precision rounding) used by precision checks
  (see `docs/PRECISION.md`).

### FR-2 Scenario demos
- Port `demos/py/demo.py` + `scenarios.py` to TS. Single source of scenario
  data: `demos/scenarios.json` (already shared with the TS demo).
- `make demo-morning-run`, `demo-evening-party`, `demo-py-output` →
  rename to `demo-ts-*`; keep `outputs` aggregate. Retain aliases for old
  target names for one release with a deprecation message.
- Output Markdown in `docs/demo_outputs/` must keep the same structure.
  Replace matplotlib/tabulate usage with ASCII/Unicode charts and plain
  Markdown table formatting (as the C and TS demos already do); no image
  output unless it is SVG generated in-process.

### FR-3 Scenario DB (`scenariogen`)
- Port `db.py`, `descriptors.py`, `mapping.py`, `references.py`, `zotero.py`,
  `build_scenario_db.py`, `query_scenario_db.py` to TS.
- Use `node:sqlite` (built in; Node ≥ 22.5). Schema, tiers (`core` 15×97,
  `full` ×193), and the `data/scenario_buffer.sqlite` path are unchanged;
  existing DB files remain readable. Note: `docs/BUILD.md` still mentions DuckDB;
  correct this as part of the docs update if the code uses SQLite.
- `references.py` data becomes a typed TS (or JSON) module; Zotero fetch uses
  global `fetch` and an XML parser only if needed (prefer JSON API; otherwise a
  small dependency such as `fast-xml-parser`).
- Make targets `scenario-db`, `scenario-db-core`, `query-demo` keep their
  variables (`MOOD`, `HUNGER`, `SLEEP`, `ACTIVITY_LVL`, `MEAL_SCHED`). While
  porting, fix `scenario-db` so it does not silently skip the build when the DB
  is absent (current `$(if $(wildcard ...))` logic is inverted).

### FR-4 Embedding search (`demo-scenario-embeddings`, `demo-time2eat`)
- Replace fastembed with `@huggingface/transformers` (ONNX runtime for Node) or
  `fastembed` JS using the same model `BAAI/bge-small-en-v1.5`, same query
  instruction prefix, cosine similarity, L2 normalization.
- These are the only targets needing network (model download on first run;
  cache under `~/.cache` / `PFUN_MODEL_CACHE`). Dependencies are declared as
  `optionalDependencies` (or a separate `npm` workspace) so `npm ci` for core
  work stays light. Document offline use.
- Acceptance: top-1 scenario for a fixed query set matches the Python
  implementation for ≥ 95 % of queries (quantization differences allowed).

### FR-5 Tests
- Port `tests/test_activity.py`, `test_demo_scenarios.py`, `test_scenariogen.py`,
  `test_scenario_db.py`, `test_precision.py` to `node:test`
  (`tests/*.test.ts`). Preserve every assertion and tolerance; do not drop
  cases. Port fixtures (`tests/data/*`) unchanged.
- `make test-scenariogen`, `test-precision`, `test` run via
  `node --experimental-strip-types --test`; add `npm test`.

### FR-6 Tools
- `tools/precision_report.py` → `tools/precision_report.ts` (output Markdown
  identical in structure).
- `tools/fetch_cgm_data.py` → `tools/fetch_cgm_data.ts` using `fetch`,
  `node:crypto` (SHA-256 verification), `node:fs`; same flags
  (`--source`, `--out`, `--url`, `--path`, `--user-id`, `--sha256`).
- `tools/convert-to-llvm.py` → `tools/convert-to-llvm.ts` (spawns
  `clang`/`llvm-as`; same outputs `build/pfun_cma_engine.{ll,bc}`). Makefile
  grouped-target rule updated to call `node` instead of `python3`.
- `tools/benchmark-compare.py` → TS. The `.so` path is benchmarked via Koffi.
  MCJIT/ORC (llvmlite) benchmarks have no Node equivalent: **decision
  required** (see §9); default is to replace them with native `clang -O2`
  (`.so`) vs. LLVM-IR/LTO builds already covered by `test-llvm`/`lto-test`, and
  WebAssembly (Node's built-in WASM engine) as the JIT comparison.
- `pfun_cma_engine/jit_engine.py`, `orc_jit_engine.py`, `demos/py/demo_jit.py`
  are removed (no llvmlite equivalent); WASM via `make demo-wasm`-style build
  with `-sENVIRONMENT=node` is the supported JIT-like path.

### FR-7 Build/packaging
- Delete `setup.py`, `pyproject.toml`, `uv.lock`, `.python-version`,
  `MANIFEST.in`, `pfun_cma_engine/__init__.py`, `pfun_cma_engine/*.py`,
  `pfun_cma_engine/py/`.
- `package.json`: add scripts (`build`→`make libs`, `test`, `demo`,
  `scenario-db`, `typecheck`), `engines`, and `devDependencies`
  (`typescript`, `@types/node`). Keep `koffi` pinned. Update
  `allowScripts` as needed.
- Optional: publish an npm package exposing the TS binding plus prebuilt
  `.so` — out of scope, tracked separately.

### FR-8 Makefile
- Remove `UV`, `PYTHON`, `python-*` targets, and `.venv` from `clean`.
- Add `NODE ?= node`, `NODE_FLAGS := --experimental-strip-types`, and reuse
  `npm-setup` (`npm ci`) as an order-only prerequisite of every TS target.
- Add a guard target that fails with a clear message when Node < 22.6.
- `make help` must still list all targets with `##` descriptions.
- `make test` must pass on a machine with **no** `python`/`python3`/`uv` on
  `PATH` (verified in CI, see §8).

### FR-9 Docker, entrypoint, Nix
- `Dockerfile`: remove `ENABLE_UV_DEMO_SETUP`, uv cache mounts, python/pip
  packages; add `nodejs npm` (Alpine) and run `npm ci` in a cached layer
  (`COPY package*.json` first). Koffi ships prebuilt musl binaries—verify, else
  add build deps.
- `entry.sh`: `shell` runs `make demo-ts-output` / `node … demos/ts/demo.ts
  --scenario "$SCENARIO"`; drop `uv run python`. (Also fix POSIX `local`/`echo
  "\n"` usage while editing.)
- `compose.yaml`: no change expected beyond build args.
- `flake.nix`: remove `python311`, `uv`, `UV*` env vars, `uv sync`, and
  `MAKEFLAGS=UV=…`; keep `nodejs_22`. Replace the `python3 -m http.server`
  preview helper with `npx http-server`/a small `node` static server script
  (`tools/serve.ts`) using `node:http`.

### FR-10 Documentation
- Update `README.md`, `docs/BUILD.md`, `docs/SCENARIO_DB.md`,
  `docs/PRECISION.md`, `PROPOSED.md`, `pfun_cma_engine/*/README.md` to remove
  every Python/uv instruction and describe the TS equivalents.
- Regenerate `docs/demo_outputs/*` via `make outputs` and review the diff.

## 6. Non-Functional Requirements

- **Dependencies:** Only Node ≥ 22.6 + npm (plus existing C/LLVM/emscripten/GSL
  toolchains). No dependency runs install scripts other than the allow-listed
  `koffi`.
- **Performance:** `build-scenario-db --tier full` wall time within 1.5× of the
  Python version; per-call engine overhead no worse than ctypes.
- **Portability:** Linux x64/arm64 (CI and Docker/Alpine), macOS. Windows
  best-effort via WSL (unchanged).
- **Security:** pin dependency versions; verify checksums for downloaded CGM
  data (existing `--sha256` behaviour); run `npm audit` in CI.
- **Reproducibility:** `package-lock.json` is the only lock file; `npm ci` is
  the install command everywhere.

## 7. Numerical Equivalence & Verification

1. Before deleting Python, capture golden outputs from the Python
   implementation for: all scenarios in `demos/scenarios.json`, `core` and
   `full` DB tiers, and the precision-report tables.
2. TS outputs must match: engine series bit-identical in FP64 (both call the
   same C code with the same inputs); derived descriptors/mappings within
   `1e-9` relative; DB row counts and labels identical; Markdown demo outputs
   identical modulo formatting changes called out in FR-2.
3. Port tests first (red/green against the Python goldens), then switch Make
   targets, then delete Python.

## 8. Acceptance Criteria

- [ ] `git grep -nEi '\b(uv|python3?|pip|pytest|numpy|venv|pyproject)\b'`
      returns only this PRD / changelog entries.
- [ ] On a container with only `gcc make clang llvm gsl nodejs npm` (no Python
      or uv): `make libs`, `make test`, `make outputs`, `make scenario-db`,
      `make query-demo`, `make precision-report`, `make fetch-cgm`,
      `make llvm-ir`, `make lto-test`, `make demo-wasm` (with emcc) succeed.
- [ ] `docker compose build && docker compose run build` and
      `docker run … shell` work without `ENABLE_UV_DEMO_SETUP`.
- [ ] `nix develop` shell contains no python/uv and `make test` passes.
- [ ] `npm run typecheck` (`tsc --noEmit`) passes.
- [ ] Ported test suite covers every test case of the Python suite
      (case-count parity documented in the PR).
- [ ] CI workflow (new `.github/workflows/ci.yml`) runs the above on a
      Python-free runner image (explicitly removing `python3` from `PATH`).
- [ ] Docs updated; `docs/demo_outputs/` regenerated.

## 9. Risks, Open Questions, Decisions Needed

| # | Item | Proposed resolution |
|---|---|---|
| R1 | llvmlite MCJIT/ORC engines and `demo_jit.py` have no Node analogue | Drop; benchmark vs. WASM and native LLVM builds. **Needs owner approval.** |
| R2 | Python package (`pip install`/wheel, ctypes wrapper) is removed — downstream Python consumers (e.g. `pfun-cma-model`) break | Confirm no consumers depend on this repo's wheel; otherwise keep a *separate* repo/branch for the Python wheel. **Needs owner approval.** |
| R3 | Embedding model in Node (ONNX runtime, model download) may differ slightly numerically | Acceptance threshold in FR-4; `optionalDependencies`. |
| R4 | `--experimental-strip-types` is experimental and forbids enums/namespaces/parameter properties | Lint rule (`erasableSyntaxOnly` in `tsconfig.json`); Node 22.18+/24 enable stripping by default—pin `engines` accordingly. |
| R5 | Koffi native prebuilds on Alpine/musl and arm64 | Verify in Docker CI matrix; fallback is building Koffi from source. |
| R6 | `node:sqlite` is stable-ish only in newer Node | Require Node ≥ 22.13 (flag-free) or use `better-sqlite3` as fallback. |
| R7 | Float16 emulation for precision tests | Implement round-to-nearest-even helper (or `Math.f16round` on Node ≥ 24); unit-test against known vectors. |

## 10. Phased Plan

1. **Phase 0 – Baseline:** capture golden outputs; add CI on current state.
2. **Phase 1 – Foundation:** `tsconfig`, `engines`, TS engine library (FR-1),
   refactor `demos/ts/demo.ts` onto it; shared test helpers.
3. **Phase 2 – Core ports:** scenarios/demo (FR-2), `scenariogen` + DB (FR-3),
   tests (FR-5), precision tool (FR-6a).
4. **Phase 3 – Tooling:** CGM fetch, LLVM conversion, benchmark, static server
   (FR-6).
5. **Phase 4 – Embeddings:** FR-4 behind optional deps.
6. **Phase 5 – Switch-over:** Makefile, Docker, entry.sh, flake, docs
   (FR-7–FR-10); regenerate outputs.
7. **Phase 6 – Removal:** delete Python sources/packaging; run the
   Python-free acceptance checks (§8).

Each phase is a separately reviewable PR that keeps `make test` green.

## 11. Out-of-Scope Follow-ups
- npm package with prebuilt binaries; WASM-only distribution of the engine;
  porting the GSL CGM fit to Node.
