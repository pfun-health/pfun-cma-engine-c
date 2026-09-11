# PROPOSED: Unified Implementation Roadmap for CMA Model Extensions

**Date:** 2026-09-06  
**Status:** Core complete, TclUI approved  
**Scope:** Activity Function Extension (complete) + LLVM IR Pipeline (Tier 1) + Review Fixes (complete) + TclUI Frontend (new)  
**Target Release:** Q3 2026 (Core / LLVM Tier 1) · Q4 2026 (TclUI Frontend)

---

## Executive Summary

This document consolidates the implementation roadmap and the approved TclUI frontend proposal:
1. **Activity Function Extension** — Physical activity modeling (**COMPLETE**).
2. **Review Findings & Required Fixes** — Three mathematical review issues (**COMPLETE**).
3. **LLVM IR Pipeline** — Compiler optimization and cross-platform support (**Tier 1 COMPLETE**; Tiers 2–3 deferred to Q4).
4. **TclUI Frontend** — Toolkit-agnostic UI spec + Tcl/Tk reference backend (**APPROVED**; canonical PRD in `TCLUI_PRD.md`, summary in §8).

### Current Implementation Status

| Component | Status | Completion | Next Action |
|-----------|--------|------------|-------------|
| **Activity functions** (`calc_A`, `calc_c_mod`, `calc_I_E_eff`) | COMPLETE | 100% | Verified in `src/pfun_cma_engine.c/h`, covered by `tests/test_activity.py` |
| **Activity integration** (`calc_G`, `run_cma_model`) | COMPLETE | 100% | Verified; `A_raw=NULL` restores exact baseline behavior |
| **Python wrapper** activity support | COMPLETE | 100% | `pfun_cma_engine.py` ctypes binding; all new signals returned |
| **Review fixes** (3 issues identified) | COMPLETE | 100% | `τ_A` guard in code; `A_raw` normalization + hepatic docs in §2/§7 |
| **LLVM IR generation** | COMPLETE | 100% | `convert-to-llvm.py` → `build/pfun_cma_engine.{ll,bc,o}` |
| **LLVM testing infrastructure** | PARTIAL | Tier 1 | `make test-llvm`, `check-ir`, `ir-metrics`; Tiers 2–3 deferred to Q4 |
| **TclUI frontend** | PLANNED | 0% | Execute §8 phases; spec frozen in `TCLUI_PRD.md` |

### High-Priority Action Items (This Sprint)

1. **Write `tclui/pfun_cma_tclui.c` engine bridge** — Tcl `pfun::` command surface (PRD §9).
2. **Implement `ui_core.tcl` logic layer** — Toolkit-free ops/state/frames + headless tests.
3. **Implement Tcl/Tk reference backend** — `backend_tk.tcl`, `theme.tcl`, `main.tcl`; feature parity with `demo.c`.
4. **Package standalone starpack** — `starpacker.tcl` pipeline → `bin/tclui-<platform>`.
5. **Regenerate `DEMO_C_OUTPUT.md`** at build time as `--ascii` conformance baseline.

---

## Section 1: Activity Function Extension

### Motivation & Physiological Context

The CMA model captures circadian and meal-driven glucose dynamics but lacks **physical activity**. Skeletal muscle contractions during activity drive insulin-independent glucose uptake (via GLUT4 translocation), elevate cortisol, and increase post-exercise insulin sensitivity.

The model operates in **nondimensional model units** (baseline ranges):
- Cortisol $`c \in [0.023, 1.234]`$ (circadian rhythm)
- Extracellular Insulin $`I_E \in [0.006, 0.564]`$
- Plasma Glucose $`G \in [0.100, 2.989]`$

Parameter values ($`\gamma_A = 0.15, \beta_A = 0.20`$, etc.) are unitless and evaluated relative to these scales.

---

## Section 2: Activity Function Design

### 2.1 Input Definition & Normalization

- **Raw input:** $`A_{\text{raw}}(t) = \text{HR}(t) \times \text{SV}_{\text{est}}(t)`$
- **Pre-normalization (Review Fix #3):** The raw formula produces values 65–260. The sigmoid expects pre-normalized input $`A_{\text{raw\_norm}} \in [0, 1]`$:
  $$`A_{\text{raw\_norm}} = \frac{\text{HR} \times \text{SV}_{\text{est}} - \text{CO}_{\text{rest}}}{\text{CO}_{\text{max}} - \text{CO}_{\text{rest}}}`$$
  yielding $`A_{\text{raw\_norm}} \approx 0`$ at rest and $\approx 1$ at maximal exercise.
- **Normalized activity signal (sigmoid):**
  $$A(t) = \frac{1}{1 + \exp(-2 k_A (A_{\text{raw\_norm}}(t) - A_{\text{thresh}}))}$$
  Defaults: $k_A = 5.0$ (gain), $A_{\text{thresh}} = 0.3$ (activation threshold), $A(t) \in (0, 1)$.

### 2.2 Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `k_A` | double | 5.0 | (0, ∞) | Activity sigmoid gain |
| `A_thresh` | double | 0.3 | [0, 1] | Activation threshold |
| `γ_A` | double | 0.15 | [0, 0.3] | Direct glucose uptake coefficient |
| `κ_A` | double | 0.5 | (0, ∞) | Glucose uptake saturation constant |
| `β_A` | double | 0.20 | [0, 1] | Cortisol amplification factor |
| `η_A` | double | 0.40 | [0, 1] | Post-activity sensitization magnitude |
| `τ_A` | double | 2.0 | (0, ∞) | Sensitization decay time constant (hours) |

### 2.3 Three Integration Pathways

#### Pathway 1: Direct Insulin-Independent Glucose Uptake
Active skeletal muscle consumes glucose via GLUT4 translocation independently of insulin:
$$\Delta G_A[i] = \frac{\gamma_A A[i]}{1 + \kappa_A A[i]}$$
Michaelis-Menten saturation form. Max reduction at $A=1$: $\gamma_A / (1 + \kappa_A) = 0.15 / 1.5 = 0.10$ (~3.3% peak $G$).  
Decreases total glucose: $G_{\text{total}}[i] = G_{\text{bias}}[i] + \sum g_j[i] - \Delta G_A[i]$.

#### Pathway 2: Activity-Modulated Cortisol
Acute exercise elevates cortisol, suppressing insulin secretion (counter-regulatory effect):
$$c_{\text{mod}}[i] = c[i] \times (1 + \beta_A A[i])$$
Multiplicative form ensures non-negativity and scales with circadian baseline. Feeds into insulin secretion: $I_S = 1 - 0.23 c_{\text{mod}} - 0.97 m$.

#### Pathway 3: Post-Activity Insulin Sensitization
Discrete recursive exponential filter modeling acute GLUT4 recovery ($s_A[0] = 0, \Delta t = t[i] - t[i-1]$):
$$s_A[i] = s_A[i-1] \exp(-\Delta t/\tau_A) + \eta_A A[i-1] (1 - \exp(-\Delta t/\tau_A))$$
Effective insulin: $I_{E,\text{eff}}[i] = I_E[i] \times (1 + s_A[i])$.  
Decay timeline ($\tau_A = 2.0\text{h}$): $0\text{h} \to 100\%$ ($s_A$ fraction), $2\text{h} \to 37\%$, $4\text{h} \to 14\%$, $8\text{h} \to 2\%$.

### 2.4 Modified Pipeline & Net Effect

```
t (time) ──► calc_L ──► calc_M ──► calc_c
                                │          │
calc_A(A_raw) ─────────► A ─────┴──► calc_c_mod ──► calc_I_S ──► calc_I_E
                                │                                   │
                                └──► calc_I_E_eff(s_A) ◄────────────┘
                                            │
calc_G(I_E_eff, A, ...) ◄───────────────────┘
```

**1-hour maximal exercise impact:**
- Direct uptake: $-0.10$ | Cortisol: $+0.02$ | Sensitization: $-0.04$ to $-0.10$
- **Fasting net:** $-0.12$ (primarily direct uptake)
- **Post-meal net:** $-0.18$ (direct uptake + sensitized insulin; 50% more effective post-meal)

### 2.5 C & Python APIs

```c
// New signal functions in pfun_cma_engine.h
void calc_A(const double* t, int N, const double* A_raw, double k_A, double A_thresh, double* out_A);
void calc_c_mod(int N, const double* c, const double* A, double beta_A, double* out_c_mod);
void calc_I_E_eff(int N, const double* I_E, const double* A, const double* t,
                  double eta_A, double tau_A, double* out_I_E_eff, double* out_s_A);

// Modified orchestration signatures
void calc_G(const double* t, int N, const double* I_E_eff, const double* A,
            const double* tM, int n_meals, const double* taug, double B, double Cm, double toff,
            double gamma_A, double kappa_A, int include_bias_in_components,
            double* out_G_instant, double* out_g_components);

void run_cma_model(
    const double* t, int N, double d, double taup, double taug_val,
    const double* taug_vec, double B, double Cm, double toff,
    const double* tM, int n_meals, int* seed, double eps,
    const double* A_raw, double k_A, double A_thresh,
    double gamma_A, double kappa_A, double beta_A, double eta_A, double tau_A,
    double* out_L, double* out_m, double* out_c, double* out_c_mod,
    double* out_A, double* out_a, double* out_I_S, double* out_I_E,
    double* out_I_E_eff, double* out_s_A, double* out_G, double* out_g);
```

```python
# pfun_cma_engine.py
def run_cma_engine_c(
    t: np.ndarray, d: float, taup: float, taug_val: float,
    taug_vec: Optional[np.ndarray] = None, B: float = 0.05, Cm: float = 0.0, toff: float = 0.0,
    tM: np.ndarray = np.array([7.0, 11.0, 17.5]), seed: Optional[int] = None, eps: float = 1e-18,
    A_raw: Optional[np.ndarray] = None, k_A: float = 5.0, A_thresh: float = 0.3,
    gamma_A: float = 0.15, kappa_A: float = 0.5, beta_A: float = 0.20,
    eta_A: float = 0.40, tau_A: float = 2.0,
) -> Dict[str, np.ndarray]:
    """Returns dict with G, g, I_E, I_E_eff, L, m, c, c_mod, A, s_A, a, I_S.
    When A_raw is None, activity terms evaluate to zero (exact backward compatibility)."""
```

---

## Section 3: Review Findings & Required Fixes (Resolved)

| Issue | Severity | Resolution Summary | Status |
|-------|----------|--------------------|--------|
| **#1: $\tau_A \le 0$ Stability Guard** | HIGH | If $\tau_A < 0$, filter exponentially grows; if $\tau_A = 0$, filter degenerates. Entry guard added to `calc_I_E_eff`: if `tau_A <= 0.0`, zero-fills $s_A$ and sets $I_{E,\text{eff}} = I_E$ (passthrough). | COMPLETE |
| **#2: Hepatic Counter-Regulation** | MEDIUM | Exercise increases hepatic glucose production (100–400%). The model currently overestimates glucose reduction during prolonged (>45m) or fasting exercise. Documented in §7; $HGP_A$ term planned for Q4 2026. | COMPLETE |
| **#3: $A_{\text{raw}}$ Normalization** | MEDIUM | $HR \times SV_{\text{est}}$ (65–260) saturates sigmoid ($A_{\text{thresh}} = 0.3$). Clarified requirement for pre-normalized $A_{\text{raw\_norm}} \in [0, 1]$ via cardiac output range in §2.1. | COMPLETE |

---

## Section 4: LLVM IR Pipeline Status

### Current Architecture
- `src/pfun_cma_engine.c` $\xrightarrow{\text{clang -S -emit-llvm -O2}}$ `build/pfun_cma_engine.ll` (15 functions, SSE2 `<2 x double>` vectors, FMA intrinsics).
- `llvm-as` / `clang` $\to$ `build/pfun_cma_engine.bc` $\to$ `build/pfun_cma_engine.o`.
- Orchestrated via `convert-to-llvm.py`.

### Testing Roadmap
- **Tier 1 — Foundation (COMPLETE):**
  - Cross-compiler numerical validation (`tests/test_scaling.c` compiled via GCC vs LLVM IR, diffed at relative tolerance $10^{-12}$; `make test-llvm`).
  - Structural IR validation via FileCheck (`.llcheck` checks vectorization, FMA, function exports; `make check-ir`).
  - Native executable generation and IR metrics tracking (`make ir-metrics`).
- **Tier 2 — Analysis (Q4 2026):**
  - Optimization pass evaluation (`opt -O2` vs `-O3` vs `-Oz`; SLP vectorizer study).
  - Cross-target compilation validation (`aarch64`, `wasm32`, `riscv64`).
  - IR static analysis (FLOP counting, memory access patterns, arithmetic intensity).
- **Tier 3 — Advanced (2027):**
  - Golden regression tracking for compiler updates.
  - Python runtime specialization via LLVM ORC JIT.
  - GPU offloading via OpenMP `#pragma omp target` or Polly.

---

## Section 5: Implementation History

Phases 1–5 of core development are complete and verified:
- **Phase 1 (Core C Functions):** Implemented `calc_A`, `calc_c_mod`, `calc_I_E_eff` (with $\tau_A \le 0$ guard), and updated `calc_G` / `run_cma_model`.
- **Phase 2 (Python Wrapper):** Added activity parameters and output buffers to ctypes wrapper; verified $A_{\text{raw}}=\text{None}$ backward compatibility.
- **Phase 3 (Documentation):** Resolved review findings #1–#3 across code and documentation.
- **Phase 4 (Validation):** Implemented unit tests for monotonicity, saturation, decay, and boundary conditions (`tests/test_activity.py`).
- **Phase 5 (LLVM Tier 1):** Configured IR generation, FileCheck structural verification, and cross-compiler test targets.

---

## Section 6: Phase Gates & Success Criteria

- [x] **Activity Core Gate:** `calc_A`, `calc_c_mod`, `calc_I_E_eff` compile; $\tau_A \le 0$ guard verified; `run_cma_model` integrates signals.
- [x] **Python Wrapper Gate:** Accepts activity parameters, returns new signals (`c_mod`, `A`, `I_E_eff`, `s_A`); backward compatible ($A_{\text{raw}}=\text{None}$).
- [x] **Documentation Gate:** Review fixes #1–#3 reflected in specifications; limitations documented.
- [x] **Validation Test Gate:** Monotonicity, saturation, decay, and boundary tests pass in `tests/test_activity.py`.
- [x] **LLVM Tier 1 Gate:** `make test-llvm` and `make check-ir` pass with zero regressions.
- [ ] **TclUI Bridge Gate:** `pfun_cma_tclui.c` outputs match Python wrapper within $10^{-12}$ rel-tol.
- [ ] **TclUI Logic Gate:** `ui_core.tcl` passes headless unit tests (ops $\to$ state $\to$ frame) with no display.
- [ ] **TclUI Parity Gate:** Tk backend satisfies all operations in PRD §6; `--ascii --save` matches `DEMO_C_OUTPUT.md`.
- [ ] **TclUI Packaging Gate:** Standalone starpack `bin/tclui-<platform>` boots and passes `--version` and `--ascii` tests.

---

## Section 7: Known Limitations & Future Work

### Limitations & Trade-offs
| Limitation | Why It Matters | Planned Resolution |
|------------|----------------|-------------------|
| **No hepatic counter-regulation** | Overestimates glucose drop in prolonged (>45m) or fasting exercise | Add hepatic glucose term $HGP_A[i] = \delta_A A(t_i)$ (50–80% uptake match) |
| **Instantaneous cortisol** | Real exercise cortisol has 20–30 min peak latency | Add first-order lag: $\tau_{\text{cort}} \dot{c}_A + c_A = \beta_A A(t)$ ($\tau \approx 0.3\text{h}$) |
| **Acute sensitization only** | Omits 12–48h gene-expression-mediated insulin sensitivity | Two-component model: $s_A = \eta_{\text{fast}} s_{\text{fast}} + \eta_{\text{slow}} s_{\text{slow}}$ |
| **No muscle glycogen tracking** | Severe glycogen depletion alters subsequent glucose uptake | Track glycogen state; modulate $\gamma_A$ dynamically |
| **Independent pathways** | Independent additive terms omit cross-inhibition | Preserved for computational speed and nondimensional tractability |

### Future Milestones
- **Q4 2026:** Hepatic glucose pathway; cortisol response delay lag; LLVM Tier 2 analysis & cross-compilation.
- **Q1 2027:** Two-component post-exercise sensitization; glycogen tracking; LLVM ORC JIT Python execution.
- **Q2 2027:** Macronutrient partitioning; WebAssembly browser demo; GPU batch acceleration.

---

## Section 8: TclUI Frontend (`pfun-cma-tclui`) — Approved Proposal

> **Canonical specification:** `TCLUI_PRD.md` (repo root). Status: **Approved 2026-09-06**.

### 8.1 Guiding Directive & Architecture
*"Make no assumption. Exhaustively define user interface operations in a way that can be readily interpreted by existing graphics implementations of all kinds."*

The UI separates into a **pure logic layer** (`ui_core.tcl`) and a **backend adapter**:
- `ui_core.tcl` ingests semantic operations (events) and emits abstract frames (render-command lists). No Tk dependencies; fully testable headless.
- Adapters supply `input_adaptor(native_event) -> op` and `view_sink(frame) -> device`.

```
native input ─► [input adaptor] ─► op (semantic) ─► ui_state ──► compose ──► FRAME ─► [view sink] ─► device
                                        │                 │
                                        └──► model run ───┘
```

### 8.2 Canonical Scenario & Parameters
- **Fixed constants:** `NMEALS=3`, `MAXPTS=512`, `EPS=1e-18`, `seed=12345`.
- **Parameters (`p0`–`p19`):** `d` (1.0), `taup` (1.2), `taug_val` (1.0), `B` (0.05), `Cm` (0.0), `toff` (0.0), `tM[0..2]` (7.0, 11.0, 17.5), `N pts` (97..512), `activity` (0/1), `A_amp` (0.4), `k_A` (5.0), `A_thresh` (0.3), `gamma_A` (0.15), `kappa_A` (0.5), `beta_A` (0.20), `eta_A` (0.40), `tau_A` (2.0), `noise` (0/1).
- **Visible curves (12):** `G, I_E, I_E_eff, L, m, c, c_mod, A, s_A, a, I_S, g`.

### 8.3 Operations at a Glance

| Group | Operations (Default Keys) |
|-------|--------------------------|
| **Focus/Nav** | `OP_FOCUS_VARLIST/PARAMS` (Tab), `OP_NEXT/PREV_ITEM` (j/k, ↑/↓), `OP_SELECT_VAR/PARAM(i)`, `OP_HELP_TOGGLE` (h), `OP_QUIT` (q) |
| **Param Edit** | `OP_PARAM_INC/DEC` (→/←, +/−), `OP_PARAM_FINE_INC/DEC` (Shift→/←, ]/[), `OP_PARAM_SET_ABS`, `OP_PARAM_TOGGLE` (Enter/Space), `OP_PARAM_RESET_ONE` (r), `OP_N_PTS_SET`, `OP_MEAL_SET` |
| **Model** | `OP_RUN_NOW` (R), `OP_AUTO_RUN_TOGGLE` (a) |
| **Plot** | `OP_PLOT_SERIES_TOGGLE` (click legend), `OP_PLOT_GRID_TOGGLE` (g), `OP_PLOT_MEALMARK_TOGGLE` (M), `OP_PLOT_INFO_AT` (hover/click), `OP_PLOT_ZOOM_X` (i/o, wheel), `OP_PLOT_PAN_X` (drag), `OP_PLOT_RESET_VIEW` (0) |
| **Persistence**| `OP_SCENARIO_SAVE/LOAD/RESET` (S/L/D), `OP_EXPORT_ASCII` (e) |
| **Pointing** | `PTR_MOVE/DOWN/UP/SCROLL/DRAG` (region hit-tested) |

All edits set `dirty`; with `auto_run=1`, the engine recomputes before next frame.

### 8.4 Render Contract & Engine Bridge
- **Regions:** `R_HEADER`, `R_VARLIST` (12), `R_PLOT`, `R_PARAMS` ($\le 6$ visible), `R_STATUS`, `R_TOAST`, `R_HELP` overlay. Minimum surface: $20 \times 12$.
- **Frame Commands:** `clear, clip, fill, frame, hline, vline, polyline, point, text, select_row, flush`.
- **Colors:** Semantic tokens (`border, grid, text, text_dim, select, highlight, series_1/2/3, warn, bg`).
- **Engine Bridge (`tclui/pfun_cma_tclui.c`):** Hand-written C extension exposing `pfun::engine version`, `pfun::default scenario`, `pfun::run scenarioDict -> resultsDict`, and granular `pfun::calc_*`. Double-Gaussian activity pulse at $t=8, 17$. Results match Python wrapper within $10^{-12}$ rel-tol.

### 8.5 Packaging & Milestones
- **Files:** `tclui/{pfun_cma_tclui.c, main.tcl, ui_core.tcl, backend_tk.tcl, theme.tcl, model.tcl, scenario.tcl, pkgIndex.tcl}`.
- **Packaging:** `packaging/starpacker` $\to$ standalone `bin/tclui-<platform>` (Linux/macOS/Windows).
- **Dev Environment:** `flake.nix` dev shell; Makefile targets `make tclui|tclui-dev|tclui-test|tclui-standalone`.

| Phase | Deliverable | Est. |
|-------|-------------|------|
| 0 | PRD + `PROPOSED.md` + scaffold `tclui/`, flake, Makefile targets | 0.5 d |
| 1 | `pfun_cma_tclui.c` engine bridge + Tcl smoke test | 1–2 d |
| 2 | `ui_core.tcl` logic layer + headless tests | 1–2 d |
| 3 | Tk backend + `demo.c` feature parity | 2–3 d |
| 4 | Activity controls, save/load, export, zoom/pan/meal markers | 1–2 d |
| 5 | Starpack packaging + headless conformance verification | 1 d |
| 6 | *(Optional)* `backend_tui.tcl` onto `term.c` | 2 d |

---

## References & Document History

### References
- **`TCLUI_PRD.md`** (repo root) — Canonical UI specification for `pfun-cma-tclui`.
- **Activity Physiology:** Richter EA, Hargreaves M (2013) *Physiol Rev* 93(3):993; Sylow L et al. (2017) *Nat Rev Endocrinol* 13(3):133; Lund S et al. (1995) *PNAS* 92(13):5817.
- **Hepatic Regulation:** Petersen KF et al. (2004) *J Clin Endocrinol Metab* 89(9):5010; Lavoie C et al. (1997) *Diabetes* 46(10):1615; Wahren J et al. (1971) *J Clin Invest* 50(12):2715.
- **LLVM:** LLVM Language Reference (llvm.org/docs/LangRef/); FileCheck Reference (llvm.org/docs/CommandGuide/FileCheck/).

### Document History
| Version | Date | Changes |
|---------|------|---------|
| 1.2 | 2026-09-09 | Condensed roadmap to $\le 500$ lines; streamlined completed phases; unified phase gates. |
| 1.1 | 2026-09-06 | Added §8 TclUI Frontend spec summary; updated core tracks to COMPLETE. |
| 1.0 | 2026-07-08 | Initial unified collation of extension proposals. |

---

**Next Step:** Begin TclUI Phase 1: `tclui/pfun_cma_tclui.c` engine bridge (§8, `TCLUI_PRD.md`).
