# PROPOSED: Unified Implementation Roadmap for CMA Model Extensions

**Date:** 2026-07-08  
**Status:** Planning Phase  
**Scope:** Activity Function Extension + LLVM IR Pipeline + Review Fixes  
**Target Release:** Q3 2026

---

## Executive Summary

This document consolidates three distinct proposal tracks into a unified implementation roadmap:

1. **Activity Function Extension** — Physical activity modeling (0% complete, HIGH priority)
2. **Review Findings & Required Fixes** — Three documented issues from mathematical review (MEDIUM priority)
3. **LLVM IR Pipeline** — Compiler optimization and cross-platform support (20% complete, LOWER priority)

### Current Implementation Status

| Component | Status | Completion | Next Action |
|-----------|--------|-----------|-----------|
| **Activity functions** (`calc_A`, `calc_c_mod`, `calc_I_E_eff`) | NOT STARTED | 0% | Implement core C functions |
| **Activity integration** in `calc_G` and `run_cma_model` | NOT STARTED | 0% | Add activity parameters to main pipeline |
| **Python wrapper** activity support | NOT STARTED | 0% | Add activity parameters to `run_cma_engine_c()` |
| **Review fixes** (3 issues identified) | NOT STARTED | 0% | Address HIGH priority guard, 2 MEDIUM docs |
| **LLVM IR generation** | EXISTS | 20% | IR generation working (`convert-to-llvm.py`) |
| **LLVM testing infrastructure** | NOT STARTED | 0% | Implement validation tests |

### High-Priority Action Items (This Sprint)

1. **Implement `calc_A()`, `calc_c_mod()`, `calc_I_E_eff()` C functions** — Core activity physics (4-6 hours)
2. **Add guard for `τ_A ≤ 0` in exponential filter** — Stability fix (0.5 hours)
3. **Update `run_cma_model()` orchestration** — Call new functions in correct order (2 hours)
4. **Document A_raw normalization path** — Clarify sigmoid input range (1 hour)
5. **Document hepatic counter-regulation limitation** — Update Known Limitations (0.5 hours)

---

## Section 1: Activity Function Extension

### Motivation

The current CMA model captures circadian and meal-driven glucose dynamics but lacks a physiologically essential dimension: **physical activity**. Skeletal muscle contractions during activity drive insulin-independent glucose uptake (via GLUT4 translocation), elevate cortisol, and increase post-exercise insulin sensitivity. Adding an activity pathway makes the model useful for exercise physiology, recovery tracking, and real-world glucose forecasting under varying activity levels.

### Physiological Context (Nondimensionalized Units)

The CMA model operates in **model units**, not real-world physiological units. Key signal ranges (from baseline model execution):

| Signal | Min | Mean | Max | Notes |
|--------|-----|------|-----|-------|
| **c** (cortisol) | 0.023 | 0.475 | 1.234 | Nondimensional circadian rhythm |
| **I_E** (insulin) | 0.006 | 0.227 | 0.564 | Nondimensional extracellular |
| **G** (glucose) | 0.100 | 1.142 | 2.989 | Nondimensional plasma level |

Parameter values (e.g., `γ_A = 0.15`, `β_A = 0.20`) are **unitless** and must be evaluated in context of model signal scales.

---

## Section 2: Activity Function Design

### 2.1 Input Definition

**Raw input:**
```
A_raw(t) = HR(t) × SV_est(t)
```
where `HR(t)` is heart rate (bpm) and `SV_est(t)` is estimated stroke volume (normalized to [0,1] fraction of resting maximum).

**Normalized activity signal (via sigmoid):**
```
A(t) = 1 / (1 + exp(-2 × k_A × (A_raw(t) - A_thresh)))
```

- `k_A = 5.0` (default) — sigmoid gain; slope at threshold = k_A/2 = 2.5
- `A_thresh = 0.3` (default) — activation threshold; half-maximal at this value
- `A(t) ∈ (0, 1)` — bounded, smooth, saturating sigmoid

**Normalization note (REVIEW FIX #3):** The `HR × SV_est` formula produces values 65–260 (rest to max). The sigmoid with `A_thresh = 0.3` expects **pre-normalized `A_raw ∈ [0, 1]`**. Recommended normalization:
```
A_raw_norm = (HR × SV_est - CO_rest) / (CO_max - CO_rest)
```
where `CO = HR × SV`. This produces `A_raw_norm ≈ 0` at rest, `≈ 1` at maximal exercise.

### 2.2 New Parameters

| Parameter | Type | Default | Description | Range | Impact |
|-----------|------|---------|-------------|-------|--------|
| `k_A` | double | 5.0 | Activity sigmoid gain | (0, ∞) | Higher = steeper transition |
| `A_thresh` | double | 0.3 | Activation threshold | [0, 1] | Activity onset point |
| `γ_A` | double | 0.15 | Direct glucose uptake coefficient | [0, 0.3] | Maximal glucose reduction |
| `κ_A` | double | 0.5 | Glucose uptake saturation constant | (0, ∞) | Saturation sharpness |
| `β_A` | double | 0.20 | Cortisol amplification factor | [0, 1] | Counter-regulatory strength |
| `η_A` | double | 0.40 | Post-activity sensitization magnitude | [0, 1] | Peak insulin enhancement |
| `τ_A` | double | 2.0 | Sensitization decay time (hours) | (0, ∞) | Recovery time constant |

### 2.3 Three Integration Pathways

#### Pathway 1: Direct Insulin-Independent Glucose Uptake

Active skeletal muscle consumes glucose via GLUT4 translocation independently of insulin.

```
ΔG_A[i] = γ_A × A[i] / (1 + κ_A × A[i])
```

**Properties:**
- Michaelis-Menten saturation form (physiologically accurate)
- Max reduction at A=1: `γ_A / (1 + κ_A) = 0.15 / 1.5 ≈ 0.10` (10% of peak glucose)
- Decreases total glucose: `G_total[i] = G_bias[i] + Σ gⱼ[i] - ΔG_A[i]`
- Non-negativity guaranteed: `ΔG_A < 0.10` with defaults

**Impact on model:**
| A | ΔG_A | Effect (% of peak) |
|----|------|-----|
| 0.0 | 0 | — |
| 0.3 | 0.060 | 2.0% |
| 0.5 | 0.075 | 2.5% |
| 1.0 | 0.100 | 3.3% |

#### Pathway 2: Activity-Modulated Cortisol

Acute exercise elevates cortisol, suppressing insulin secretion (counter-regulatory effect).

```
c_mod[i] = c[i] × (1 + β_A × A[i])
```

**Properties:**
- Multiplicative form: keeps cortisol non-negative
- Scales proportionally to baseline circadian cortisol
- Avoids spurious nocturnal elevation
- Feeds into: `I_S = 1 - 0.23 × c_mod - 0.97 × m`

**System-level effect (at maximal exercise A=1):**
- Cortisol increase: `×1.20` (20%)
- Insulin secretion decrease: `I_S ↓ 0.06` (proportional to cortisol boost)
- Meal glucose increase: `+0.02 to +0.04` (small counter-regulatory effect, competed by direct uptake and sensitization)

#### Pathway 3: Post-Activity Insulin Sensitization

After activity, tissue remains more insulin-sensitive for 2-4 hours (acute GLUT4 recovery phase).

**Recursive exponential filter:**
```
s_A[0] = 0
s_A[i] = s_A[i-1] × exp(-dt/τ_A) + η_A × A[i-1] × (1 - exp(-dt/τ_A))
```

**Properties:**
- Discrete-time implementation of: `τ_A · ds_A/dt + s_A = η_A · A(t)`
- `s_A[i] ∈ [0, η_A)` — bounded sensitization state
- Time-convolved effect: peak at activity onset, decays to baseline

**Effective insulin:**
```
I_E_eff[i] = I_E[i] × (1 + s_A[i])
```

**Recovery timeline (with τ_A = 2.0h, η_A = 0.40):**
| Time post-exercise | s_A fraction | I_E_eff multiplier | Meal glucose effect |
|-|-|-|-|
| 0h (peak) | 100% | ×1.40 | ↓0.10 |
| 2h | 37% | ×1.15 | ↓0.04 |
| 4h | 14% | ×1.05 | ↓0.015 |
| 8h | 2% | ×1.007 | negligible |

**Scope clarification:** This models **acute GLUT4 recovery** (1-4h time constant), NOT the 12-48h gene-expression-mediated sensitization (HKII upregulation, AS160 signaling). For future work, a two-component model can capture both phases.

**Known limitation:** Real exercise cortisol has 20-30 minute latency to peak. Current model assumes instantaneous response. Future work: add first-order lag with τ ≈ 0.3h.

### 2.4 Modified Model Pipeline

```
t (time vector)
│
├── calc_L  ──►  L (Light)
│
├── calc_M  ──►  m (Melatonin)     [unchanged]
│
├── calc_c  ──►  c (Cortisol)
│
│   ★ NEW: calc_A ──►  A(t) activity signal
│   (from A_raw via sigmoid)
│
│   ★ NEW: calc_c_mod ──►  c_mod[i] = c[i] × (1 + β_A × A[i])
│   [activity-elevated cortisol]
│
├── calc_a  ──►  a (Adiponectin)   [unchanged]
│
├── calc_I_S ──►  I_S = 1 - 0.23×c_mod - 0.97×m
│   [uses modified cortisol]
│
├── calc_I_E ──►  I_E = a × I_S    [unchanged]
│
│   ★ NEW: calc_I_E_eff ──►  I_E_eff[i] = I_E[i] × (1 + s_A[i])
│   [post-activity sensitization]
│
└── calc_G  ──►  G = G_bias + Σ gⱼ - ΔG_A
    [subtract contraction-mediated uptake, use I_E_eff instead of I_E]
```

**New intermediate signals:**
- `A(t)` — normalized activity signal (size N)
- `c_mod(t)` — activity-modified cortisol (size N, replaces `c` downstream)
- `s_A(t)` — post-activity sensitivity state (size N, internal to filter)
- `I_E_eff(t)` — activity-sensitized insulin (size N, replaces `I_E` in glucose calculation)

### 2.5 Net Effect (Example)

**One hour of maximal exercise:**

| Pathway | Mechanism | Glucose change (model units) |
|---------|-----------|-----|
| Direct uptake | ΔG_A subtraction | **−0.10** |
| Cortisol | c_mod → I_S↓ → I_E↓ → meal G↑ | **+0.02** (small counter-reg) |
| Sensitization | I_E_eff↑ → meal G↓ | **−0.04 to −0.10** |
| **Net (fasting, low I_E)** | | **−0.12** (mostly direct uptake) |
| **Net (post-meal, high I_E)** | | **−0.18** (direct + sensitization) |

**Physiological interpretation:** Exercise is 50% more effective at lowering glucose in the post-meal state than in the fasting state — matches known physiology.

### 2.6 API Changes

#### C API (`pfun_cma_engine.h`)

**New signal functions:**
```c
void calc_A(const double* t, int N, const double* A_raw,
            double k_A, double A_thresh, double* out_A);

void calc_c_mod(int N, const double* c, const double* A,
                double beta_A, double* out_c_mod);

void calc_I_E_eff(int N, const double* I_E, const double* A,
                  const double* t, double eta_A, double tau_A,
                  double* out_I_E_eff, double* out_s_A);
```

**Modified `calc_G` signature:**
```c
void calc_G(const double* t, int N, const double* I_E_eff,  // ★ uses I_E_eff
            const double* A,                                  // ★ NEW activity
            const double* tM, int n_meals,
            const double* taug, double B, double Cm, double toff,
            double gamma_A, double kappa_A,                  // ★ NEW activity params
            int include_bias_in_components,
            double* out_G_instant, double* out_g_components);
```

**Updated `run_cma_model` signature:**
```c
void run_cma_model(
    const double* t, int N,
    double d, double taup, double taug_val,
    const double* taug_vec,
    double B, double Cm, double toff,
    const double* tM, int n_meals,
    int* seed, double eps,
    const double* A_raw,              // ★ NEW: raw activity input
    double k_A, double A_thresh,      // ★ NEW: activity sigmoid params
    double gamma_A, double kappa_A,   // ★ NEW: glucose uptake params
    double beta_A,                    // ★ NEW: cortisol amplification
    double eta_A, double tau_A,       // ★ NEW: post-activity sensitization
    double* out_L, double* out_m, double* out_c, double* out_c_mod,
    double* out_A,                    // ★ NEW: normalized activity
    double* out_a, double* out_I_S, double* out_I_E,
    double* out_I_E_eff,             // ★ NEW: sensitized insulin
    double* out_s_A,                 // ★ NEW: sensitivity state
    double* out_G, double* out_g
);
```

**Note on `calc_G` parameter change:** The second parameter was `I_E`; now `I_E_eff`. However, the implementation receives a generic `const double*` pointer, so this is a semantic/documentation change, not a breaking change. The pipeline correctly passes `I_E_eff` after activity processing.

#### Python API (`pfun_cma_engine.py`)

```python
def run_cma_engine_c(
    t: np.ndarray,
    d: float,
    taup: float,
    taug_val: float,
    taug_vec: Optional[np.ndarray] = None,
    B: float = 0.05,
    Cm: float = 0.0,
    toff: float = 0.0,
    tM: np.ndarray = np.array([7.0, 11.0, 17.5]),
    seed: Optional[int] = None,
    eps: float = 1e-18,
    # ★ NEW activity parameters
    A_raw: Optional[np.ndarray] = None,
    k_A: float = 5.0,
    A_thresh: float = 0.3,
    gamma_A: float = 0.15,
    kappa_A: float = 0.5,
    beta_A: float = 0.20,
    eta_A: float = 0.40,
    tau_A: float = 2.0,
) -> Dict[str, np.ndarray]:
```

**Returns:**
```python
return {
    "G": out_G,
    "g": out_g.reshape((n_meals, N)),
    "I_E": out_I_E,
    "I_E_eff": out_I_E_eff,   # ★ NEW
    "L": out_L,
    "m": out_m,
    "c": out_c,
    "c_mod": out_c_mod,       # ★ NEW
    "A": out_A,               # ★ NEW
    "s_A": out_s_A,           # ★ NEW
    "a": out_a,
    "I_S": out_I_S,
}
```

**Backward compatibility:** When `A_raw` is `None`, activity effects are disabled (all activity terms evaluate to zero), preserving exact backward compatibility with the current model.

---

## Section 3: Review Findings & Required Fixes

Comprehensive mathematical review conducted 2026-07-04 identified **3 genuine issues** (1 HIGH, 2 MEDIUM). All require resolution before implementation.

### Issue #1: HIGH Priority — `τ_A ≤ 0` Stability Guard

**Severity:** HIGH  
**File:** `calc_I_E_eff` implementation  
**Problem:** If `τ_A < 0`, the exponential decay becomes exponential growth:
```
s_A[i] = s_A[i-1] × exp(-dt/τ_A) = s_A[i-1] × exp(+dt/|τ_A|) > 1
```
This causes `s_A` to grow without bound (unstable filter). If `τ_A = 0`:
```
s_A[i] = η_A × A[i-1]
```
(instantaneous tracking, no smoothing — degenerate).

**Fix:** Add guard at function entry:
```c
if (tau_A <= 0.0) {
    // Sensitization disabled — passthrough
    for (int i = 0; i < N; i++) {
        out_s_A[i] = 0.0;
        out_I_E_eff[i] = I_E[i];  // No sensitization
    }
    return;
}
```

**Testing:** Verify that `τ_A = 0` produces identical output to disabling sensitization (`η_A = 0`); verify negative `τ_A` raises error or silently disables.

---

### Issue #2: MEDIUM Priority — Missing Hepatic Counter-Regulation Documentation

**Severity:** MEDIUM  
**File:** PROPOSED.md — add "Known Limitations" section  
**Problem:** During exercise, the liver increases glucose production by:
- 100% (doubles) at mild exercise (30–45% VO₂max)
- 100–200% at moderate exercise (55–65% VO₂max)
- 200–400% (3–5× rest) at heavy exercise (>75% VO₂max)

Without this mechanism, the model predicts **net glucose reduction** without accounting for hepatic compensation. For short-duration exercise (10–30 min), the error is small. For prolonged exercise (>45 min) or fasting conditions, the model overestimates glucose reduction.

**Fix:** Add "Known Limitations" section documenting this constraint and conditions where it matters (prolonged exercise, fasting state).

**Future work:** Implement hepatic term:
```
HGP_A[i] = δ_A × A(t[i])       // additive to G_bias
```
tuned so hepatic output rises to match 50–80% of muscle uptake, maintaining homeostasis.

**References:**
- Petersen et al. (2004) *J Clin Endocrinol Metab* 89(9):5010–5016
- Lavoie et al. (1997) *Diabetes* 46(10):1615–1623
- Wahren et al. (1971) *J Clin Invest* 50(12):2715–2725

---

### Issue #3: MEDIUM Priority — A_raw Normalization Path Ambiguity

**Severity:** MEDIUM  
**File:** PROPOSED.md Section 2 (Activity Input Definition)  
**Problem:** The proposal defines `A_raw(t) = HR(t) × SV_est(t)` but the sigmoid expects pre-normalized `A_raw ∈ [0, 1]`:

| Condition | HR (bpm) | SV_est | A_raw | Sigmoid issue |
|-----------|----------|--------|-------|---|
| Rest | 65 | 1.0 | 65 | WAY above threshold 0.3 |
| Walking | 110 | 1.25 | 138 | Saturates sigmoid |
| Running | 160 | 1.35 | 216 | Saturates sigmoid |

With `A_thresh = 0.3`, ANY activity yields `A(t) ≈ 1` — sigmoid cannot distinguish walking from running.

**Fix:** Add explicit normalization formula to documentation:
```
A_raw_norm = (HR·SV_est - CO_rest) / (CO_max - CO_rest)
```
where `CO_rest ≈ 65` (resting cardiac output), `CO_max ≈ 260` (maximal). This produces:
- Rest: `A_raw_norm = 0` → `A(t) ≈ 0.047` (residual from sigmoid baseline)
- Brisk walk: `A_raw_norm ≈ 0.3` → `A(t) ≈ 0.5` (threshold)
- Max exercise: `A_raw_norm = 1` → `A(t) ≈ 0.999` (saturated)

**Alternative:** For pre-normalized input (if caller handles normalization), use simpler clip form:
```c
A(t) = clip(A_raw(t), 0, 1)
```

**Implementation:** Support both paths via a normalization flag or separate function.

---

## Section 4: LLVM IR Pipeline Status

### Current State

The LLVM IR pipeline exists but is **20% complete** — IR generation works, testing infrastructure missing.

| Component | Status | Path |
|-----------|--------|------|
| Conversion tool | EXISTS | `convert-to-llvm.py` (153 lines) |
| LLVM IR output (text) | EXISTS | `build/pfun_cma_engine.ll` (1136 lines) |
| LLVM Bitcode (binary) | EXISTS | `build/pfun_cma_engine.bc` |
| Object file | EXISTS | `build/pfun_cma_engine.o` |
| Testing infrastructure | NOT STARTED | — |
| Cross-compiler validation | NOT STARTED | — |
| Structural IR validation | NOT STARTED | — |

**Build pipeline:**
```
src/pfun_cma_engine.c ──[clang -S -emit-llvm -O2]──▶ build/pfun_cma_engine.ll
                         ──[llvm-as or clang]────────▶ build/pfun_cma_engine.bc
```

**Generated IR characteristics:**
- 15 functions (all C functions mapped to IR)
- Auto-vectorization: `<2 x double>` (SSE2) in `calc_I_S`, `calc_I_E`
- LLVM intrinsics: `llvm.fmuladd.f64`, `llvm.fmuladd.v2f64`, `llvm.assume`
- External calls: `@exp`, `@pow`, `@log`, `@cos`, `@malloc`, `@free`
- Toolchain: clang 22.1.6, target x86-64, C99, `-O2`

### Testing Roadmap

#### Tier 1 — Foundation (HIGH priority, Week 1)

1. **Numerical correctness validation** — Cross-compiler comparison
   - Compile `experiments/test_scaling.c` against `.ll` IR using clang
   - Run both GCC and LLVM binaries, diff outputs with FP tolerance
   - Add `make test-llvm` target to Makefile
   - Integrate into CI for regression detection

2. **Structural IR validation** — LLVM FileCheck patterns
   - Verify auto-vectorization in `calc_I_S`, `calc_I_E` (check for `<2 x double>`)
   - Verify FMA intrinsics present (`llvm.fmuladd.*` calls)
   - Verify all 15+ functions exist in module
   - Verify no unintended external function calls
   - Create `.llcheck` file with patterns
   - Add `make check-ir` target

3. **Native executable pipeline** — Formalize `.ll` → binary
   - Add `make test-llvm` target that builds and runs test
   - Provides first meaningful `make test` output

#### Tier 2 — Analysis (MEDIUM priority, Week 2)

4. **LLVM `opt` pass exploration** — Understand which optimizations matter
   - Run individual optimization passes on IR
   - Measure instruction count, basic block count
   - Evaluate SLP vectorizer effectiveness beyond clang auto-vectorization
   - Compare `-O2` vs `-O3` vs `-Oz` effects

5. **Cross-target compilation** — Demonstrate portability
   - ARM64: `llc -mtriple=aarch64-linux-gnu`
   - WebAssembly: `llc -mtriple=wasm32`
   - RISC-V: `llc -mtriple=riscv64-linux-gnu`
   - Value: mobile/browser/embedded deployment paths

6. **IR static analysis** — Computational profile extraction
   - FLOP count per function
   - Memory access patterns
   - Pointer aliasing analysis (TBAA metadata)
   - Vector lane utilization
   - Estimated arithmetic intensity

#### Tier 3 — Advanced (LOWER priority, Week 3+)

7. **Optimization regression suite** — Golden value tracking
   - Track: instruction count, vectorized loops, FMA intrinsics, external calls
   - Alert on unexpected changes (e.g., compiler upgrade)

8. **ORC JIT runtime compilation** — Runtime specialization (Python)
   - Load `.bc` bitcode at runtime
   - Compile to native code via LLVM ORC JIT
   - Execute directly from Python (no `.so` intermediate)
   - Enable parameter-specific optimization

9. **GPU offloading** — Computational parallelization
   - Target embarrassingly parallel loops (`calc_G`, `calc_L`)
   - OpenMP `#pragma omp target` directives OR Polly polyhedral optimizer
   - Effort: high; potential speedup: significant

### Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|----------|
| LLVM version mismatch | IR incompatibility | Pin LLVM version; document requirements |
| FP differences (GCC vs clang) | False positives in validation | Use relative tolerance (`rtol=1e-12`) |
| FileCheck patterns brittle | Test maintenance burden | Test only stable IR properties |
| ORC JIT complexity | High effort | Prototype simplest case first |

---

## Section 5: Implementation Roadmap

### Phase 1: Activity Function Core Implementation (Week 1–2)

**Effort:** ~16–20 hours  
**Deliverables:** Core C functions, integration, backward compatibility

| Task | Effort | Owner | Acceptance Criteria |
|------|--------|-------|---|
| Implement `calc_A()` | 1.5 h | dev | Sigmoid normalizes `A_raw` to [0,1) with correct defaults |
| Implement `calc_c_mod()` | 1 h | dev | Cortisol amplification: `c_mod = c × (1 + β_A × A)` |
| Implement `calc_I_E_eff()` with guard | 2 h | dev | Exponential filter; `τ_A ≤ 0` guard prevents instability |
| Modify `calc_G()` | 2 h | dev | Accept activity parameters; subtract `ΔG_A`; use `I_E_eff` |
| Update `run_cma_model()` orchestration | 2 h | dev | Call functions in correct order; manage buffers |
| Add HIGH priority fix (τ_A guard) | 0.5 h | dev | ✓ Implemented above |
| **Subtotal** | **~8.5 h** | | |

**C Function Specifications:**

```c
/* calc_A: Normalize raw activity signal via sigmoid */
void calc_A(const double* t, int N, const double* A_raw,
            double k_A, double A_thresh, double* out_A) {
    // For i = 0 to N-1:
    //   if A_raw == NULL: out_A[i] = 0
    //   else: out_A[i] = 1 / (1 + exp(-2 * k_A * (A_raw[i] - A_thresh)))
}

/* calc_c_mod: Activity-modulated cortisol */
void calc_c_mod(int N, const double* c, const double* A,
                double beta_A, double* out_c_mod) {
    // For i = 0 to N-1:
    //   out_c_mod[i] = c[i] * (1 + beta_A * A[i])
}

/* calc_I_E_eff: Post-activity insulin sensitization (exponential filter) */
void calc_I_E_eff(int N, const double* I_E, const double* A,
                  const double* t, double eta_A, double tau_A,
                  double* out_I_E_eff, double* out_s_A) {
    // Guard: if tau_A <= 0, zero-fill s_A and copy I_E to I_E_eff (passthrough)
    // Otherwise:
    //   s_A[0] = 0
    //   For i = 1 to N-1:
    //     dt = t[i] - t[i-1]
    //     decay = exp(-dt / tau_A)
    //     s_A[i] = s_A[i-1] * decay + eta_A * A[i-1] * (1 - decay)
    //     out_I_E_eff[i] = I_E[i] * (1 + s_A[i])
}
```

**Integration into `run_cma_model()` (call order):**
```c
calc_L(...)
calc_M(...)
calc_c(...)
calc_A(...)                    // ★ NEW
calc_c_mod(...)                // ★ NEW (uses c and A)
calc_a(...)                    // uses c_mod instead of c
calc_I_S(...)                  // uses c_mod
calc_I_E(...)
calc_I_E_eff(...)              // ★ NEW (uses I_E and A)
calc_G(..., I_E_eff, A, ...)   // ★ MODIFIED: uses I_E_eff and activity params
```

### Phase 2: Python Wrapper Update (Week 2)

**Effort:** ~4–6 hours  
**Deliverables:** Activity parameters in Python API, new outputs in return dict

| Task | Effort | Owner | Acceptance Criteria |
|------|--------|-------|---|
| Add activity parameters to Python function signature | 1 h | dev | `A_raw`, `k_A`, `A_thresh`, `gamma_A`, `kappa_A`, `beta_A`, `eta_A`, `tau_A` |
| Allocate output buffers for new signals | 1 h | dev | `out_c_mod`, `out_A`, `out_I_E_eff`, `out_s_A` |
| Call C functions in correct order | 1 h | dev | Pipeline matches C orchestration above |
| Return new signals in dict | 0.5 h | dev | `"c_mod"`, `"A"`, `"I_E_eff"`, `"s_A"` in returned dict |
| Test backward compatibility | 1 h | qa | `A_raw=None` produces identical output to current model |
| **Subtotal** | **~4.5 h** | | |

### Phase 3: Documentation & Review Fixes (Week 2)

**Effort:** ~3–4 hours  
**Deliverables:** Updated PROPOSED.md, review fixes addressed

| Task | Effort | Owner | Acceptance Criteria |
|------|--------|-------|---|
| Add A_raw normalization formula (Fix #3) | 1 h | scribe | Explicit formula with example values; clarify [0,1] expectation |
| Document hepatic counter-regulation limitation (Fix #2) | 0.5 h | scribe | "Known Limitations" section; list conditions (prolonged exercise, fasting) |
| Document τ_A scope (acute vs long-term sensitization) | 0.5 h | scribe | Clarify 2-4h time constant, mention future two-component model |
| High priority fixes verification (Fix #1) | 0.5 h | qa | Verify `τ_A ≤ 0` guard implemented and tested |
| **Subtotal** | **~2.5 h** | | |

### Phase 4: Validation Tests (Week 3)

**Effort:** ~4–6 hours  
**Deliverables:** Comprehensive validation test suite

| Task | Effort | Owner | Acceptance Criteria |
|------|--------|-------|---|
| Backward compatibility test | 1 h | qa | `A_raw=None` bit-identical output |
| Monotonicity test | 1 h | qa | Increasing `A_raw` strictly decreases glucose, increases cortisol |
| Saturation test | 1 h | qa | At `A=1`, `ΔG_A` saturates at `γ_A/(1+κ_A)` |
| Decay test | 1 h | qa | Post-activity sensitivity decays to baseline within `~4×τ_A` |
| Edge case tests | 1 h | qa | `A_raw=0`, `γ_A=0`, `β_A=0`, `η_A=0`, `τ_A=0.1` |
| Integration test (full model) | 1 h | qa | Run full pipeline; check all outputs non-NaN, in expected ranges |
| **Subtotal** | **~6 h** | | |

### Phase 5: LLVM Testing Infrastructure (Week 3–4, LOWER priority)

**Effort:** ~8–10 hours  
**Deliverables:** Foundation tier testing (Tier 1 from §4)

| Task | Effort | Owner | Notes |
|------|--------|-------|-------|
| Cross-compiler numerical validation | 1 h | dev | `make test-llvm` target; diff with tolerance |
| FileCheck structural tests | 1.5 h | dev | `.llcheck` patterns; `make check-ir` target |
| Integrate into Makefile | 0.5 h | dev | Update test target; CI setup |
| **Subtotal** | **~3 h** (Foundation only) | | |

**Tier 2–3 (Analysis & Advanced) deferred to Q4.**

---

## Section 6: Phase Gates & Success Criteria

### Phase 1 Gate (Completion of core C functions)

**Must-pass criteria:**
- [ ] All three activity functions (`calc_A`, `calc_c_mod`, `calc_I_E_eff`) compile and run without crashes
- [ ] `run_cma_model()` orchestrates activity functions in correct order
- [ ] `τ_A ≤ 0` guard prevents instability (tested)
- [ ] Activity outputs (`out_A`, `out_c_mod`, `out_I_E_eff`, `out_s_A`) are allocated and filled

**Verification method:** Unit tests for each function + integration smoke test

### Phase 2 Gate (Python wrapper ready)

**Must-pass criteria:**
- [ ] `run_cma_engine_c()` accepts all new activity parameters
- [ ] New signals returned in dict: `"c_mod"`, `"A"`, `"I_E_eff"`, `"s_A"`
- [ ] Backward compatibility preserved: `A_raw=None` produces identical output (relative tolerance 1e-14)

**Verification method:** Python pytest suite with before/after comparison

### Phase 3 Gate (Documentation complete)

**Must-pass criteria:**
- [ ] PROPOSED.md updated with all three fixes
- [ ] A_raw normalization path documented with formula
- [ ] Hepatic counter-regulation listed in Known Limitations
- [ ] τ_A scope (acute vs long-term) clarified

**Verification method:** Document review + link check

### Phase 4 Gate (Validation complete)

**Must-pass criteria:**
- [ ] All 4 validation tests pass (backward compat, monotonicity, saturation, decay)
- [ ] Edge case tests pass (zero parameters, boundary conditions)
- [ ] Full model integration test passes (non-NaN outputs, in expected ranges)

**Verification method:** Automated pytest suite; manual spot-check of outputs

### Release Gate (Ready for merge)

**Must-pass criteria:**
- [ ] All 4 phases complete and passing
- [ ] Code review passed (mathematical soundness + implementation quality)
- [ ] CI/CD pipeline green (build, tests, linting)
- [ ] Backward compatibility confirmed (all existing tests pass)

---

## Section 7: Known Limitations & Future Work

### Current Scope Limitations

| Limitation | Why It Matters | Future Work |
|-----------|---|---|
| **No hepatic counter-regulation** | Model unidirectional (uptake only) — overestimates glucose reduction in prolonged/fasting exercise | Add `HGP_A[i] = δ_A × A(t)` term tuned to 50–80% muscle uptake |
| **Instantaneous cortisol response** | Real cortisol has 20–30 min latency to peak | Add first-order lag: `dc_A/dt = (β_A × A(t) - c_A) / τ_cort` with `τ_cort ≈ 0.3h` |
| **Acute sensitization only (2–4h)** | Doesn't capture 12–48h gene-expression-mediated effects | Two-component model: `s_A = η_fast × s_A_fast + η_slow × s_A_slow` with `τ_slow ≈ 24h` |
| **No muscle glycogen depletion** | Very intense exercise depletes muscle glycogen, affecting subsequent glucose uptake | Track glycogen state; modulate `γ_A` as function of glycogen level |
| **No nutrient partitioning** | Exercise affects amino acid uptake and fat oxidation in addition to glucose | Out of scope for CMA model; extension to macronutrient partitioning |

### Physiological Accuracy Trade-offs

The model **prioritizes** computational efficiency and nondimensional tractability over exhaustive physiological detail. Specifically:

- **Additive activity pathways** (uptake + cortisol + sensitization) are **independent** in the model but interact in real physiology (e.g., high cortisol inhibits GLUT4 translocation)
- **Sigmoid normalization** assumes sub-threshold linearity and super-threshold saturation; real dose–response curves may differ
- **Exponential decay** of sensitization is simplified; real recovery includes GLUT4 recycling, AMPK signaling decay, mitochondrial adaptation

These are acceptable given the model's nondimensional scope and intended use cases (exercise forecasting, glucose dynamics education).

### Future Enhancement Roadmap

**Q4 2026:**
- Add hepatic glucose production pathway
- Implement cortisol response delay (first-order lag)
- Expand LLVM testing to Tier 2–3 (analysis, cross-target compilation)

**Q1 2027:**
- Two-component post-exercise sensitization (acute + long-term)
- Muscle glycogen state tracking
- ORC JIT integration for Python runtime compilation

**Q2 2027:**
- Macronutrient partitioning extension (lipids, amino acids)
- GPU offloading via LLVM for batch simulations
- Browser-based WebAssembly demo (LLVM → WASM pipeline)

---

## Section 8: Implementation Checklist

### Pre-Implementation

- [ ] All stakeholders reviewed and approved this roadmap
- [ ] Mathematical correctness of activity functions spot-checked
- [ ] Review fixes (3 issues) understood and prioritized
- [ ] Resources allocated (dev, QA, scribe)

### Phase 1: C Functions

- [ ] `calc_A()` implemented and unit-tested
- [ ] `calc_c_mod()` implemented and unit-tested
- [ ] `calc_I_E_eff()` with `τ_A ≤ 0` guard implemented and tested
- [ ] `calc_G()` modified to accept activity parameters
- [ ] `run_cma_model()` orchestration updated (correct call order)
- [ ] Integration test: full pipeline runs without crash

### Phase 2: Python Wrapper

- [ ] Activity parameters added to `run_cma_engine_c()` signature
- [ ] New output buffers allocated
- [ ] C functions called from Python in correct order
- [ ] New signals returned in output dict
- [ ] Backward compatibility test: `A_raw=None` bit-identical
- [ ] Integration test: Python wrapper works end-to-end

### Phase 3: Documentation

- [ ] Fix #1 (τ_A guard): Verified in code
- [ ] Fix #2 (hepatic limitation): Documented in Known Limitations
- [ ] Fix #3 (A_raw normalization): Formula + example added to PROPOSED.md
- [ ] Section 7 (Future Work) added with enhancement roadmap
- [ ] This document (unified PROPOSED.md) finalized

### Phase 4: Validation

- [ ] Backward compatibility test passes
- [ ] Monotonicity test passes
- [ ] Saturation test passes
- [ ] Decay test passes
- [ ] Edge case tests pass
- [ ] Full integration test passes

### Phase 5: LLVM (Lower priority, Q3 if time permits)

- [ ] `make test-llvm` target implemented
- [ ] Cross-compiler validation script written
- [ ] FileCheck structural tests created
- [ ] CI integration: new test targets run in pipeline

### Release Readiness

- [ ] Code review: mathematical soundness ✓
- [ ] Code review: implementation quality ✓
- [ ] CI/CD: all tests passing ✓
- [ ] Backward compatibility: verified ✓
- [ ] Documentation: complete and clear ✓

---

## References & Links

### Activity Function Design
- Richter EA, Hargreaves M (2013). "Skeletal Muscle as Glucose Buffer in the Whole Body." *Physiol Rev* 93(3):993–1017. PMID: 23899560
- Sylow L, et al. (2017). "Exercise-stimulated glucose uptake—Regulation and implications for glycemic control." *Nat Rev Endocrinol* 13(3):133–148. PMID: 27739515
- Lund S, et al. (1995). "Contraction stimulates translocation of glucose transporter GLUT4 in skeletal muscle." *PNAS* 92(13):5817–5821. PMID: 7597034

### Hepatic Counter-Regulation
- Petersen KF, et al. (2004). "Contributions of hepatic and peripheral insulin resistance to the pathogenesis of impaired fasting glucose." *J Clin Endocrinol Metab* 89(9):5010–5016.
- Lavoie C, et al. (1997). "Effects of glucose infusion on hormonal changes during exercise." *Diabetes* 46(10):1615–1623.
- Wahren J, et al. (1971). "Splanchnic and leg blood flow and metabolism in mildly diabetic patients." *J Clin Invest* 50(12):2715–2725. PMID: 5129313

### LLVM Infrastructure
- LLVM Language Reference Manual: https://llvm.org/docs/LangRef/
- LLVM Optimizer Passes: https://llvm.org/docs/Passes/
- FileCheck Documentation: https://llvm.org/docs/CommandGuide/FileCheck/

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-07-08 | Scribe | Unified collation of PROPOSED*.md into single roadmap |
| — | 2026-07-04 | Build Orchestrator | Review findings (PROPOSED.changes.md) |
| — | — | — | PROPOSED.md, PROPOSED_CMA_EXT.md (duplicate activity proposals) |
| — | — | — | PROPOSED_LLVM.md (LLVM testing roadmap) |

---

**Status:** Ready for stakeholder review  
**Next step:** Executive approval; begin Phase 1 implementation
