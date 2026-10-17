# PRD: Migrate All Python-Based Build Targets to Node.js / TypeScript

**Status:** In progress — Phase 1 (foundation) implemented; Phases 2–6 and the
Cloudflare direction (§11) remain. See §10 for per-phase status.
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
  `flake.nix` (kept, as dev-environment config only), docs and tracked
  packaging files.
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

## 3a. Build Target Pruning (Minimum Set for Defined Demos)

> **Amendment (supersedes the removals below where they conflict):** the
> `/time2eat` demo is now a **required deliverable** (see §11.7), shipped as a
> Cloudflare Worker app. Therefore the scenario database, embedding search and
> `time2eat` logic are **kept and ported to TypeScript** (FR-3, FR-4 apply in
> full, and `demo-scenario-embeddings`, `demo-time2eat`, `scenario-db`,
> `scenario-db-core`, `query-demo`, `test-scenariogen` move from "Remove" to
> "Keep" as TS targets). `demos/py/{time2eat,scenario_embeddings_demo,
> build_scenario_db,query_scenario_db}.py`, `demos/py/scenariogen/**`, the
> scenario tests and `docs/SCENARIO_DB.md` are ported (docs retained and
> updated), then the Python originals are deleted. Everything else in the
> Remove list (JIT, IR exploration, precision, packaging) is unchanged. R8 is
> narrowed accordingly.

Defined demos: C interactive (`demos/c/demo.c`), CGM fit (`demos/c/cgm_fit.c`),
WASM browser (`demos/c/wasm_demo.c`), and TypeScript scenario demo
(`demos/ts/demo.ts`, which absorbs the morning-run / evening-party scenarios
from `demos/scenarios.json`). The Python-only demos (`demo_jit.py`, scenario
DB, embeddings, `/time2eat`) are not required demos and are removed rather
than ported, which narrows FR-3, FR-4 and FR-6 (see below).

**Keep (required by a defined demo or its verification):**

| Target | Reason |
|---|---|
| `help`, `libs`, `all`, `directories`, `clean`, `rebuild` | Core build; `libs` feeds the TS demo (Koffi) |
| `demo`, `vendor-nuklear`, `demo-c-output` | C demo |
| `demo-ts-output` (+ `demo-morning-run`, `demo-evening-party` re-pointed at TS), `npm-setup`, `outputs` | TS demo and snapshots in `docs/demo_outputs/` |
| `demo-wasm` | WASM demo |
| `cgm-ingest`, `cgm-fit`, `test-cgm` | CGM fit demo and its test |
| `test`, `test-llvm`, `check-ir` (+ `llvm-ir`, `llvm-verify`) | Minimal regression gate: C engine numerics via `tests/test_scaling.c`, plus a ported `test-ts` for the TS demo/scenarios |
| `format`, `check-format` | Source hygiene |

**Remove (not needed by any defined demo):**
- Python env: `python-setup`, `python-setup-dev`, `python-clean-venv`,
  `demo-py-output`, and variables `UV`, `PYTHON`.
- Scenario DB / embeddings: `scenario-db`, `scenario-db-core`, `query-demo`,
  `demo-scenario-embeddings`, `demo-time2eat`, `test-scenariogen`, plus
  `demos/py/**`, `demos/py/scenariogen/**`, `docs/SCENARIO_DB.md`,
  and the `SCENARIO_DB` / `MOOD` / `HUNGER` / `SLEEP` / `ACTIVITY_LVL` /
  `MEAL_SCHED` variables.
- Precision tooling: `test-precision`, `precision-report`, `tools/precision_report.py`,
  `docs/PRECISION.md` (revisit only if the owner wants it kept as a TS test).
- Data fetch: `fetch-cgm`, `tools/fetch_cgm_data.py` (sample CSVs in
  `tests/data/` already cover the CGM demo).
- LLVM exploration: `lto-test`, `llvm-targets`, `analyze-ir`, `optimize-ir`,
  `profile-ir`, `ir-metrics`, `analyze-all`, and `tools/ir-*.sh`,
  `tools/check-ir-metrics.sh`, `tests/ir-golden-metrics.txt` — optional
  analysis, not demo-required. `convert-to-llvm.py` is replaced by a
  direct `clang -S -emit-llvm` / `llvm-as` recipe in the Makefile, so no
  script (Python or TS) is needed for `llvm-ir`.
- Python packaging and JIT: `setup.py`, `pyproject.toml`, `uv.lock`,
  `.python-version`, `MANIFEST.in`, `pfun_cma_engine/*.py`,
  `pfun_cma_engine/py/`, `tools/benchmark-compare.py`, `tests/*.py`.
- Debug target: `debug` (rebuild via `make CFLAGS=...` instead).

**Effect on other sections:** FR-3 (scenario DB), FR-4 (embeddings), FR-5
(ported tests limited to `test_activity`/`test_demo_scenarios` equivalents
exercising the TS demo), and FR-6 (only `convert-to-llvm` replaced inline;
`precision_report`, `fetch_cgm_data`, `benchmark-compare` dropped) shrink to
the surface above; `node:sqlite`, embedding dependencies and R1/R3/R6/R7 no
longer apply. Docker `build`/`shell` and `flake.nix` shrink accordingly. The
removal list needs owner sign-off (new open decision R8); anything the owner
wants preserved is re-added to the Keep table and ported per the original FRs.

## 3b. File Removal Manifest

Principle: a tracked file stays only if a kept demo/target (§3a), the dev
environment, or documentation of those needs it. Preliminary-phase JIT/IR/LLVM
experiments are removed. Each deletion is done with `git rm` in the phase
noted; before deleting, `git grep` each path to confirm no remaining
reference (Makefile, docs, Docker, flake).

**Delete (Phase 6 unless noted):**

| Group | Files |
|---|---|
| JIT engines | `pfun_cma_engine/jit_engine.py`, `pfun_cma_engine/orc_jit_engine.py`, `demos/py/demo_jit.py` |
| IR/LLVM exploration scripts | `tools/ir-pass-explorer.sh`, `tools/ir-profile.sh`, `tools/check-ir-metrics.sh`, `tests/ir-golden-metrics.txt`, `tools/benchmark-compare.py` |
| LLVM conversion script | `tools/convert-to-llvm.py` (replaced by an inline Makefile recipe; Phase 5) |
| Python packaging | `setup.py`, `pyproject.toml`, `uv.lock`, `.python-version`, `MANIFEST.in`, `pfun_cma_engine/__init__.py`, `pfun_cma_engine/pfun_cma_engine.py`, `pfun_cma_engine/py/` |
| Python demos / scenario DB | `demos/py/**` (incl. `scenariogen/`), `docs/SCENARIO_DB.md` |
| Python tests | `tests/test_activity.py`, `test_demo_scenarios.py`, `test_scenariogen.py`, `test_scenario_db.py`, `test_precision.py` (coverage ported per FR-5 first; Phase 2 port, Phase 6 delete) |
| Precision / data tools | `tools/precision_report.py`, `docs/PRECISION.md`, `tools/fetch_cgm_data.py` |
| Python-only facade/docs | `pfun_cma_engine/c/README.md`, `pfun_cma_engine/ts/README.md` are folded into the main README, then removed along with the now-empty `pfun_cma_engine/{c,py,ts}` dirs (the built `.so`/`.a` output dir `pfun_cma_engine/` stays, or moves to `build/lib/` — decide in Phase 1 and update the Koffi path) |

**Review candidates (audit during Phase 0; delete if unreferenced by kept
targets, the dev shell, or docs):**
- `tools/docker-build.sh`, `tools/docker-run.sh` (keep only if Docker is a
  supported demo path), `compose.yaml`, `Dockerfile`, `entry.sh`.
- `TCLUI_PRD.md`, `PROPOSED.md` (planning docs for a UI not in the demo set;
  archive/delete, trimming PROPOSED.md references to Python/JIT).
- `docs/FORMATTING.md`, `.vscode/settings.json` (remove Python settings).
- `third_party/nuklear/nuklear.h` — **keep** (C demo, also fetched by
  `vendor-nuklear`).
- `src/fit/pfun_cma_fit.c`, `src/pfun_cma_cgm.c`, `tests/test_cgm.c`,
  `tests/data/*` — **keep** (CGM demo).
- `docs/demo_outputs/*` for removed demos (`DEMO_PY_OUTPUT.md`, etc.) —
  delete; regenerate the rest.

**Keep list (explicit):** `src/**`, `include/**`, `Makefile`, `flake.nix`,
`flake.lock`, `package.json`, `package-lock.json`, `demos/c/**`,
`demos/ts/**`, `demos/scenarios.json`, `public/index-wasm.html`,
`tests/test_scaling.c`, `tests/ir-structural-check.llcheck` (backs the kept
`check-ir`), `tests/test_cgm.c`, `README.md`, `docs/BUILD.md`.

**Acceptance for removals:** after Phase 6, `git ls-files` contains no `*.py`,
`*.toml` Python config, `uv.lock`, or `jit`/`orc` named files; every remaining
tracked file is reachable from a kept target, the dev shell, or the docs
(verified by a short audit script/checklist in the PR); `make help` lists only
kept targets.

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
- **Implemented** in `pfun_cma_engine/ts/engine.ts`: loads
  `pfun_cma_engine/libpfun_cma_engine.so` (path overridable by
  `PFUN_CMA_ENGINE_LIB`); errors clearly if not built (`run make libs`).
  Exports `runCmaEngine(input)`, `MAX_POINTS` (768), `libraryPath()`, and the
  `ModelParams`/`ActivityParams`/`EngineInput`/`EngineOutput` types. Input
  validation: 2..`MAX_POINTS` time points, `mealWidths.length === meals.length`
  (`RangeError` otherwise). `demos/ts/demo.ts` now uses it (output verified
  byte-identical for `morning-run`). Covered by `tests/engine.test.ts`.
- Remaining: a higher-level `run_cma_engine_c`-compatible wrapper with the
  Python defaults (parameter defaults, activity-pulse generation) for the
  scenario/DB ports.
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
- `flake.nix` (**retained** as the development-environment definition; it is
  not a build or CI dependency, and no `make` target may require Nix):
  - `devShells.default`: `gcc`, `gnumake`, `pkg-config`, `gsl`,
    `clang-tools`, `llvmPackages.{clang,llvm}` (for `llvm-ir`, `test-llvm`,
    `check-ir`), and `nodejs_22` (pinned ≥ 22.6; consider 24 for flag-free
    type stripping). Remove `python311`, `uv`, `UV`/`UV_PYTHON*` env vars,
    the `MAKEFLAGS=UV=…` override, and the `uv sync --dev` hook; replace the
    hook with `[ -d node_modules ] || npm ci`. Drop pruned-target tooling
    (§3a) that no kept target needs.
  - `devShells.wasm`: unchanged opt-in `emscripten` shell (`EM_CACHE` kept);
    fix the shell-hook hints so they name real commands.
  - `packages` (`pfun-cma-engine`, `demo-wasm`) stay for reproducible demo
    builds; they must not reference Python.
  - `apps.serve-wasm`: replace `python3 -m http.server` with a `node`
    static server (`tools/serve.ts` via `pkgs.nodejs_22`), so the flake
    closure is Python-free.
  - Update the header comment ("native C/Python/TS work" → "native C/TS
    work"), run `nix flake check`, and refresh `flake.lock` only if inputs
    change.
  - `docs/BUILD.md` Nix section updated to say Nix is optional and provides
    the dev shell only.

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
| R9 | Deleting files is irreversible in the working tree and drops historical experiments (JIT/IR) | Preserve in git history; tag `pre-node-migration` before Phase 6; owner reviews the §3b manifest |
| R8 | Pruning (§3a) deletes scenario DB, embeddings, precision and LLVM-analysis features | Owner confirms the Keep/Remove lists before Phase 6 |
| R7 | Float16 emulation for precision tests | Implement round-to-nearest-even helper (or `Math.f16round` on Node ≥ 24); unit-test against known vectors. |

## 10. Phased Plan

1. **Phase 0 – Baseline:** capture golden outputs; add CI on current state.
   *(Not started.)*
2. **Phase 1 – Foundation:** `tsconfig`, `engines`, TS engine library (FR-1),
   refactor `demos/ts/demo.ts` onto it; shared test helpers.
   *(Done: `tsconfig.json` (strict, `erasableSyntaxOnly`), `engines.node
   >=22.6`, `typescript`/`@types/node` devDependencies, npm scripts `build`,
   `test` (`node --test tests/*.test.ts`), `typecheck` (`tsc --noEmit`);
   Python code and Makefile untouched.)*
3. **Phase 2 – Core ports** *(next)*: scenarios/demo (FR-2), `scenariogen` + DB (FR-3),
   tests (FR-5), precision tool (FR-6a).
4. **Phase 3 – Tooling:** CGM fetch, LLVM conversion, benchmark, static server
   (FR-6).
5. **Phase 4 – Embeddings:** FR-4 behind optional deps.
6. **Phase 5 – Switch-over:** Makefile, Docker, entry.sh, flake, docs
   (FR-7–FR-10); regenerate outputs.
7. **Phase 6 – Removal:** delete Python sources/packaging; run the
   Python-free acceptance checks (§8).

Each phase is a separately reviewable PR that keeps `make test` green.

## 11. Future Direction: Cloudflare Workers WASM Deployment

**Status:** Future work (post-migration). Not part of Phases 0–6; it builds on
their output (Python-free toolchain, kept `demo-wasm` target, Node tooling).

### 11.1 Goal
Serve the CMA model (including the `/time2eat` chat recommender, §11.7) as a tiny, scale-to-zero edge app on Cloudflare Workers,
running the existing C engine compiled to WebAssembly. Targets:
- **Minimal memory:** a few MB resident per isolate (well below the Workers
  128 MB isolate limit); no heap growth at runtime.
- **Minimal process overhead:** no containers/VMs, no always-on server, no
  external services (no DB, KV, or embeddings), stateless pure compute.
- **Minimal cost:** stay within the Workers free tier for demo traffic; on the
  paid plan, per-request CPU time is the cost driver, so each call must cost
  well under 1 ms of CPU.

The engine already suits this: `demos/c/wasm_demo.c` uses fixed static buffers
(`MAXPTS 512`, ~16 `double` arrays ≈ 65 KB total) and `run_cma_model` is a
deterministic closed-form computation with no I/O or threads.

### 11.2 Platform facts to design against
Re-verify against the Cloudflare docs at implementation time (limits change):
- Workers run in V8 isolates; WASM is supported via `.wasm` module imports
  bundled by Wrangler (`import mod from "./x.wasm"` yields a precompiled
  `WebAssembly.Module`). Runtime compilation of arbitrary bytes
  (`WebAssembly.compile`/`instantiate(bytes)`) is blocked, so the module must
  be imported statically; instantiate once at module scope and reuse.
- Isolate memory limit is 128 MB; Workers are single-threaded (no wasm
  threads/shared memory).
- Free plan CPU time is ~10 ms/request; paid plan allows far more but bills per
  CPU-ms. Script size limits are small on the free plan (single-digit MB
  compressed) and larger on paid — check current numbers; our artifact should
  be far below either.
- Static HTML/JS can be served via Workers Static Assets (static asset
  requests are free/unmetered at time of writing — verify).
- WASI/Emscripten syscalls are not available; the module must not depend on
  filesystem, threads, or dynamic memory growth.

### 11.3 Architecture
```
client ──GET /──────────► Static Assets (index.html, small JS)
client ──POST /api/run──► Worker (TS) ──► cma.wasm (C engine, instance reused)
```
- One Worker (`worker/index.ts`) with two routes: static UI via Assets binding,
  and `POST /api/run` taking the model parameters as JSON, returning series as
  JSON (or a compact `Float32Array` binary response for large `npts`).
- Alternatively (zero Worker CPU): run the WASM in the browser only and deploy
  **only static assets** (the existing `public/index-wasm.html` +
  `demo-wasm.{js,wasm}`). This is the cheapest option and the recommended
  phase 1; the Worker API is optional phase 2 for programmatic access.

### 11.4 Technical steps
1. **Standalone WASM build** (new Make target `wasm-worker`):
   build `src/pfun_cma_engine.c` plus a thin export shim (derived from
   `wasm_demo.c`, with the input validation/clamping kept) using either
   `clang --target=wasm32 -nostdlib -O3 -flto -Wl,--no-entry
   -Wl,--export-dynamic` with a small libm (or emscripten
   `-sSTANDALONE_WASM=1 -sMALLOC=none -sINITIAL_MEMORY=1MB
   -sALLOW_MEMORY_GROWTH=0 -sFILESYSTEM=0 --no-entry`). Prefer the
   no-libc/no-emscripten-glue route so no JS glue is shipped; supply `exp`,
   `pow`, `sin`, `cos`, etc. via a minimal libm (e.g. compiler-rt/musl subset)
   or JS imports (`Math.*`) if bit-exact parity is not required (decision in
   step 5).
2. **Shrink:** `-Oz`/`-O3` + LTO, `wasm-opt -Oz` (Binaryen), strip names;
   record artifact size and enforce a budget (e.g. ≤ 100 KB, CI check).
3. **Memory layout:** fixed 1–2 pages (64–128 KiB) of linear memory, static
   input/output buffers exposed as exported offsets; JS reads results through
   typed-array views over `memory.buffer` (no per-request allocation).
   Reject `npts > MAXPTS` with HTTP 400.
4. **Worker** (`worker/index.ts`, `wrangler.toml`/`wrangler.jsonc`):
   static `.wasm` import, module-scope `new WebAssembly.Instance`, request
   validation (finite numbers, range clamps), JSON in/out, `Cache-Control` and
   `Cache API` / ETag on deterministic GET variants so repeat queries cost zero
   CPU. No bindings (KV/D1/R2/DO) are configured. Set `compatibility_date`,
   disable observability sampling beyond what is needed.
5. **Parity tests:** reuse the `node:test` suite to load the same `.wasm` under
   Node and compare against the native `.so` output via Koffi (tolerance
   documented; exact for FP64 if libm matches, else ~1e-12 relative).
6. **Local dev & CI:** `wrangler dev` for local; `npm run deploy` →
   `wrangler deploy`; CI job builds the wasm, runs parity tests, checks size
   budget, and (on main) deploys using a scoped `CLOUDFLARE_API_TOKEN` secret.
   Add `wrangler` as a `devDependency`; Nix dev shell includes Node only
   (wrangler via npm).
7. **Cost/footprint guardrails:** rate-limit with a Cloudflare rate-limiting
   rule or WAF; cap `npts`; benchmark CPU time per request with
   `wrangler tail`/analytics and record p50/p99 in docs; alert if p99 CPU
   approaches the free-tier limit.
8. **Docs:** `docs/DEPLOY_CLOUDFLARE.md` (setup, token scope, deploy, rollback);
   README link.

### 11.7 Required: `/time2eat` as a user-facing Worker app
**Requirement:** the deployed app must provide a functional `/time2eat`:
a real user asks "when is the best time for me to eat?" and receives
recommended meal times, backed by the CMA model and scenario database. It is a
port of `demos/py/time2eat.py` (nearest-scenario anchor → alternatives sharing
non-meal descriptors + similarity-weighted top-k neighbors → score by
time-in-range of the precomputed glucose curve → return best `tM` meal onsets).

**Components** (one Worker with internal modules, or two Workers joined by a
service binding; default to one Worker to minimize cost/latency):

1. **Chat orchestrator (LLM).** Handles the conversation: greets, extracts
   structured state (`sleep`, `activity`, `mood`, `hunger`, `meal_schedule`,
   plus any allowed free text), detects missing/ambiguous fields, asks concise
   follow-up questions, and only calls the recommender once the required
   fields are satisfied or the user explicitly opts to use defaults. It never
   invents physiology: numeric answers come only from the recommender tool.
   - Model access via Workers AI (`env.AI`, no external keys, billed per use)
     as default; provider abstracted behind an `LlmClient` interface so an
     external API (via AI Gateway for caching/rate limits/spend caps) can be
     swapped in.
   - Uses structured output / tool calling: a single tool
     `recommend_mealtimes(state)` with a JSON schema whose enums are the
     dimension descriptors from the DB; the orchestrator validates the model's
     tool args against the schema before executing and re-prompts on failure.
   - Small context: system prompt + last N turns only; hard cap on output
     tokens, turns per session, and message length.
   - Safety/medical: system prompt and UI state the output is informational
     and not medical advice; users reporting diabetes/medication/hypoglycemia
     symptoms get a fixed safety message instead of a recommendation. Refuse
     off-topic requests.
2. **Recommender service (embedding model + scenario DB + WASM engine).**
   Deterministic, no LLM. Inputs: validated state → output: `{anchor,
   alternatives[], best: {meal_schedule, tM[], tir, similarity}, curve?}`.
   - **Scenario DB at the edge:** the DB is built offline (`make scenario-db`,
     TS) and shipped as read-only data. Preferred: a compact precomputed
     bundle (JSON/binary: scenario descriptors, tM, glucose curves, and
     precomputed embedding vectors, Float32 or int8-quantized) imported as a
     static asset or Worker module — no DB at request time. Fallback: D1 (SQLite)
     loaded from the same build output if the corpus outgrows the bundle.
     Scenario count (core 15 / full tier) × 97–193 points keeps this well
     under a few MB.
   - **Embeddings:** the corpus is embedded *at build time*. At request time
     only the user's text must be embedded: use Workers AI
     (`@cf/baai/bge-small-en-v1.5`, same family as the Python demo; apply the
     BGE query instruction prefix, L2-normalize) and do cosine search in-Worker
     over the preloaded vectors (a few hundred floats × tens of scenarios —
     microseconds, no vector DB needed; Vectorize only if the corpus becomes
     large). Better still, avoid the embedding call: the LLM's structured
     descriptors map directly to scenario keys, and embeddings are used only to
     resolve free-text residue. Cache query→embedding in the Cache API.
   - **WASM engine:** the §11.4 module recomputes curves for on-the-fly
     variants (e.g. ± meal shifts not in the DB) so scoring is not limited to
     precomputed scenarios.
   - TIR target range defaults to the reference scenario's 5th–95th glucose
     percentile, overridable, as in the Python demo.

**Interfaces**
- `POST /api/chat` `{session_id?, messages[]}` → streamed or JSON assistant
  reply plus optional `recommendation` object.
- `POST /api/time2eat` `{state}` → recommendation (direct, LLM-free API;
  also used by tests and by the orchestrator tool).
- `GET /` UI: minimal static chat page (no framework) calling `/api/chat`;
  recommendation card shows meal times and a small SVG glucose curve.
- Session state is carried client-side (message history in the request) so
  the Worker stays stateless; no Durable Objects/KV unless rate limiting
  requires them.

**Cost & footprint controls (extend §11.1):** one LLM call per user turn
(≤ 2 when a retry is needed), capped tokens; embedding call only when free
text cannot be resolved by descriptors; per-IP/session rate limiting;
AI Gateway spend cap; response caching for identical states
(`/api/time2eat` is pure → cacheable); no always-on components.

**Privacy:** no persistence of chats by default; no PII or health data logged;
logs record only counts/latency. Document data handling in
`docs/DEPLOY_CLOUDFLARE.md`.

**Technical steps (add to §11.4):**
9. Port `scenariogen` + `time2eat` logic to TS as a runtime-agnostic library
   (no Node-only APIs on the recommender path) used by both the Node CLI
   (`make demo-time2eat`) and the Worker.
10. Add `make scenario-bundle`: builds the DB, embeds the corpus with the
    chosen model, quantizes, and emits the Worker data bundle plus a manifest
    (model name, dims, hash, build date); Worker refuses to start on a model/
    dimension mismatch.
11. Implement the `LlmClient`, prompt, tool schema, slot-filling state
    machine (required fields, defaults, max follow-ups = 3), and safety
    handling; unit-test with a recorded/mock LLM.
12. Implement `/api/time2eat` and `/api/chat`; wire the static UI.
13. Evaluation: golden-query set for the recommender (top-1 anchor and best
    `tM` match the Python reference ≥ 95%); conversation test set checking
    that missing info triggers a follow-up, complete info triggers exactly one
    tool call, and out-of-scope/medical prompts get the safe response.

**Acceptance criteria (in addition to §11.5):**
- [ ] A user can open the deployed URL, ask "when is the best time for me to
      eat?", answer follow-ups, and receive meal-time recommendations with
      anchor scenario and TIR score.
- [ ] Recommender output is deterministic for a given state and matches the
      Python reference on the golden set.
- [ ] LLM never returns numbers not produced by the recommender (verified by
      test: response times ⊆ tool result times).
- [ ] ≤ 2 LLM calls and ≤ 1 embedding call per user turn; per-turn p50 CPU
      (excluding AI waits) < 10 ms.
- [ ] Rate limiting and spend cap configured; no chat data persisted.
- [ ] Works with Workers AI only (no external secrets) and with the swap-in
      provider behind `LlmClient`.

**Risks:** LLM hallucination or non-compliance with schema (mitigate with
validation + tool-only numerics); Workers AI model availability/pricing
changes (abstraction + AI Gateway); corpus growth beyond bundle size (D1/
Vectorize fallback); medical-advice liability (disclaimer + hard safety path).

### 11.5 Acceptance criteria
- [ ] `.wasm` ≤ 100 KB (stretch ≤ 50 KB), no JS glue beyond the Worker.
- [ ] Linear memory fixed ≤ 2 MiB; no growth; Worker RSS reported by the
      platform far below 128 MB.
- [ ] p99 CPU time per `/api/run` (97 pts) < 1 ms locally in Node/workerd.
- [ ] Zero configured storage/compute bindings; deployable on the free plan.
- [ ] Parity tests pass against the native engine within stated tolerance.
- [ ] `make wasm-worker` and `npm run deploy` work without Python or uv.

### 11.6 Risks / open questions
- **libm without Emscripten:** exactness vs. size trade-off (step 1).
- **Free-plan CPU ceiling (~10 ms):** large `npts` or noisy runs must be
  bounded; mitigated by the `MAXPTS` cap and caching.
- **Limits drift:** verify size/CPU/memory/pricing numbers at implementation
  time; they are reference values, not guarantees.
- **Abuse/cost:** public unauthenticated endpoint needs rate limiting.

## 12. Out-of-Scope Follow-ups
- npm package with prebuilt binaries; WASM-only distribution of the engine;
  porting the GSL CGM fit to Node.
