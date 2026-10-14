# Scenario Database Buffer (`scenariogen`)

Precomputed, queryable SQLite buffer of physiological scenarios for the PFun CMA
engine. Each scenario is a fully-resolved set of engine parameters (free
parameters + explicit defaults + descriptor-derived overrides) evaluated by the
C engine, so clients can run their own parameter sweeps without owning any of
the peer-reviewed mapping logic.

---

## Design goals

1. **Deterministic** — the same engine commit and descriptor registry produce
   byte-identical buffers (`precompute` is pure; `A_raw=None` → no RNG).
2. **Evidence-backed** — every non-default descriptor carries a per-parameter
   override with a rationale and a `ref_id` into the local `citations` registry
   (`parameter_overrides` mirrors `scenariogen/mapping.py::OVERRIDES`).
3. **Local-first references** — references are curated locally (Zotero SQLite +
   manual additions). The seed policy enforces `local > 4 * web` with `web >= 3`
   as a floor; `origin` in `citations` records the provenance.
4. **Fast client lookup** — exact + nearest-match lookup over the full
   descriptor space in milliseconds, with a long-format view for plotting.

## Descriptor space

5 dimensions, 19 descriptors → **768 combinations** (4 × 4 × 4 × 3 × 4).

| Dimension | Values (default in bold) |
|-----------|--------------------------|
| `activity` | sedentary (**sedentary**), light, moderate, vigorous |
| `hunger` | sated, **neutral**, hungry, starving |
| `meal_schedule` | **standard**, skipped_breakfast, late_dinner, heavy_dinner |
| `mood` | stressed, tired, **neutral**, happy |
| `sleep` | poor, short, **restful** |

`core` tier materializes the calibration scenario plus single-descriptor
excursions (15 scenarios); `full` tier precomputes all 768.

## Parameter channels

Descriptors modify engine parameters through `Override` rows
(`param_name`, `op` ∈ {set, add, mul}, `value`, `rationale`, `ref_id`).
Verified examples from the buffer's `parameter_overrides`:

| Channel | Descriptor | Effects (op value) | Rationale ref(s) |
|---------|-----------|--------------------|------------------|
| `mood → taup, B` | stressed | `taup` ×0.80, ×1.00; `B` ×1.03 | russell2019stress, feder2004cortisol, strilka2016stress |
| `mood → taup, B` | tired | `taup` ×0.90, `B` ×1.02 | vanleeuwen2010sleep |
| `mood → taup` | happy | `taup` ×1.10 | steptoe2007affect |
| `hunger → B, taug_vec, tM` | starving | `B` ×1.15, `taug_vec` ×1.20, `tM` −0.5 | goldstone2009fasting, henderson2013meal |
| `hunger → B, taug_vec` | sated | `B` ×0.92, `taug_vec` ×0.90 | brunstrom2011satiety |
| `sleep → taup, B` | short | `taup` ×0.85, `B` ×1.04 | vanleeuwen2010sleep, qian2018circadian |
| `activity → gamma_A, beta_A, eta_A, tau_A, pulses` | vigorous | γ_A 0.20, β_A 0.20, η_A 0.60, τ_A 4.0 | sylow2017exercise, richter2013glut4, frampton2021exercise |
| `meal_schedule → tM, taug_vec, B` | late_dinner | `tM` [7, 11, 20.5], `taug_vec` [1, 1, 1.2] | zecevic2023timing, bandin2014meal |

The full machine-readable registry lives in
`demos/py/scenariogen/mapping.py::OVERRIDES` and is seeded verbatim into
`parameter_overrides` (with `rationale` and `ref_id` for every row).

## Engine semantics: what the buffer contains

Each scenario stores the raw engine outputs at `n_pts` time points
(`t`, `G`, `g_meals` per-meal components, `I_E`, `I_E_eff`, `L`, `m`,
`c`, `c_mod`, `A`, `s_A`, `a_insulin`, `I_S`) plus precomputed `summary` JSON
stats (`G_mean/G_max/G_p05/G_p95`, `t_G_max`, `max_meal_excursion`,
`g_auc_total`, `I_E_eff_max`, `c_mean/c_max`, `A_peak/A_auc`, …).

Two engine characteristics are worth knowing when selecting features:

- **Meal pulses are zero exactly at the meal time.** `K_pfun(x) = exp(-ln(2x)²)`
  for `x > 0`, else 0; the component peaks at `tM + taug²/2`. Prefer
  `g_auc_total` / `max_meal_excursion` over point samples for prandial load.
- **`I_E_eff_max` saturates w.r.t. meal size.** `I_E_eff = I_E · (1 + s_A)`
  with `I_E = a · I_S`; the day-max is pinned by insulin sensitivity
  (mood/sleep via `I_S`, activity via `s_A`) and does not discriminate hunger.
  Hunger-driven differences surface in the **glucose-side** stats
  (`g_auc_total`, `G_mean`, `G_max`).

Verified directions on the `full` buffer:

| Comparison | Result |
|------------|--------|
| `mood:stressed` vs `mood:neutral` | avg `c_mean` 0.463 vs 0.451 (cortisol tone up) |
| `activity:vigorous` vs `sedentary` | avg `A_auc` 2.12 vs 0.00 |
| `hunger` sated < neutral < hungry < starving | avg `g_auc_total` 3.45 < 3.60 < 3.73 < 3.95 |

## Schema

| Table | Purpose |
|-------|---------|
| `dimensions` / `descriptors` | Dimension registry; descriptor id, label, ordinal |
| `parameter_overrides` | `(descriptor_id, param_name, op, value, rationale, ref_id)` |
| `citations` | Curated registry (`ref_id, title, authors, year, journal, doi, url, origin, zotero_item_id, local_pdf_path`) |
| `descriptor_refs` / `scenario_refs` | Evidence links (role `descriptor mapping`) |
| `model_parameters` | Engine free-parameter catalogue (`domain`, `is_free`) |
| `scenarios` | Wide rows: descriptor set, resolved `params`, engine arrays, `summary` JSON, `status`, `created_at` |
| `scenario_timecourses_long` | Long view (`scenario_id, t, G, g, a, …`) via `unnest` for plotting |
| `meta` | key/value build metadata (`generator, tier, n_scenarios, n_pts, t_start`, …) |

Scenario lookup: `scenario_id` (unique integer), `slug`
(`mood=stressed__hunger=starving__sleep=restful__activity=sedentary__meal_schedule=standard`),
and `descriptor_set` (JSON string). Partial descriptor sets are allowed —
unspecified dimensions fall back to their defaults — with `_match_distance`
reporting how many descriptors had to default.

## Build & query

```sh
# full buffer (768 × 193 points) — this is the default artifact
.venv/bin/python demos/py/build_scenario_db.py --db data/scenario_buffer.sqlite

# small core buffer (15 × 97 points) for tests/CI
.venv/bin/python demos/py/build_scenario_db.py --db /tmp/scenario_core.sqlite --tier core

# query: exact + nearest match, summary, timecourse, references
.venv/bin/python demos/py/query_scenario_db.py --db data/scenario_buffer.sqlite \
  --mood stressed --hunger starving --sleep restful --activity sedentary --meal-schedule standard \
  --summary-only --timecourse --references
```

Makefile conveniences: `make scenario-db-core`, `make scenario-db`,
`make query-demo`, `make test-scenariogen` (see `make help`).

## Tests

- `tests/test_scenariogen.py` — descriptor catalog shape, override integrity,
  rationale/ref completeness, resolution determinism, label/form validation,
  per-dimension physiological effects, unknown-descriptor rejection.
- `tests/test_scenario_db.py` — schema, seeded counts, local-first ratio,
  Zotero enrichment, tier precompute (`core`=15, `full`=768), engine parity vs
  direct `run_cma_engine_c` (atol 1e-12), determinism, lookup, timecourse view,
  physiological directions.
- `make test` additionally runs the C-side LLVM numerical + IR checks.

## Reproducibility

`precompute(conn, tier=..., t=...)` is pure with respect to the engine and the
registry: identical git state + identical override table ⇒ byte-identical
buffers (covered by `test_precompute_is_deterministic`). Rebuild with
`replace=True`; the artifact is disposable.