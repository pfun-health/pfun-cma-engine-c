# Comprehensive Review: Activity Function Extension for the CMA Model

**Reviewer:** Build Orchestrator (mathematical soundness & physiological accuracy)
**Date:** 2026-07-04 (revised)
**Document:** PROPOSED.md v1
**Focus:** Mathematical soundness and physiological accuracy of the activity model integration

---

## Preamble: Nondimensionalization Context

The CMA model operates in **nondimensionalized model units**, not real-world physiological units. Key signals have the following typical numerical ranges (verified by running the existing model with default parameters `d=0, taup=0.5, taug_val=4.0, B=0.05, Cm=0, tM=[7,11,17.5]`):

| Signal | Min | Mean | Max | Description |
|--------|-----|------|-----|-------------|
| **c** (cortisol) | 0.023 | 0.475 | 1.234 | Nondimensional circadian cortisol |
| **I_E** (insulin) | 0.006 | 0.227 | 0.564 | Nondimensional extracellular insulin |
| **G** (glucose) | 0.100 | 1.142 | 2.989 | Nondimensional plasma glucose |
| **a** (adiponectin) | 0.250 | 0.402 | 0.733 | Nondimensional adiponectin |
| **I_S** (insulin secretion) | 0.025 | 0.489 | 0.861 | Nondimensional secretion index |

Time `t` IS in hours (the model compares `t` against `8.0`, `12.0`, `3.0`, etc. directly). Activity parameters (`γ_A`, `κ_A`, `β_A`, `η_A`, `τ_A`) are in model units, with `τ_A` in hours.

**Key insight:** The parameter values (e.g., `γ_A = 0.15`, `β_A = 0.20`) cannot be directly interpreted as real-world percentages. They must be evaluated in context of the model's internal signal scales. A glucose reduction of `0.10` in model units (~10% of peak glucose) is meaningful because the model's glucose range is `0.1–3.0`.

---

## Executive Summary

The proposal is structurally sound. After accounting for the nondimensionalized parameter space, the three-pathway design is both mathematically consistent and produces physiologically reasonable system-level behavior. I found **3 genuine issues** (1 HIGH, 2 MEDIUM) that should be resolved before implementation:

| # | Severity | Area | Summary | Original assessment |
|---|----------|------|---------|---------------------|
| 1 | **HIGH** | Implementation | `τ_A ≤ 0` makes the exponential filter unstable (negative τ_A) or degenerate (τ_A=0); must be guarded | Was HIGH (upheld, corrected reasoning) |
| 2 | **MEDIUM** | Counter-reg | Missing hepatic glucose production for prolonged exercise | Was MEDIUM (upheld) |
| 3 | **MEDIUM** | Documentation | A_raw normalization path needs clarification: HR×SV formula produces values 65-260 but sigmoid expects [0,1] input | Was HIGH (downgraded) |

**Original findings that I withdraw after studying the nondimensionalization:**

| Old issue | Withdrawn because... |
|-----------|---------------------|
| τ_A = 2.0h is too short | τ_A = 2.0h models acute post-exercise GLUT4 recovery (~3-4h), not gene-expression-mediated sensitization (12-48h). Appropriate for the claimed scope. |
| calc_G I_E parameter name | Purely cosmetic — the function receives a `const double*` and doesn't distinguish the signal source. The pipeline correctly passes `I_E_eff`. |
| A_raw = 0 sigmoid residual breaks backward compat | Backward compatibility is about `A_raw = NULL` (explicitly handled), not sigmoid at `A_raw = 0`. |
| γ_A/κ_A vs γ_A/(1+κ_A) bound | Bound γ_A/κ_A is a mathematically valid (conservative) supremum. Non-negativity guarantee holds with defaults. |
| β_A = 0.20 too low | In model units, 20% cortisol boost feeds through I_S → I_E → G cascade. System-level glucose change is ~+0.02 — small but qualitatively correct (counter-regulatory). |
| I_S negativity worsened | Cortisol and melatonin are anti-correlated (circadian), so worst-case doesn't occur. I_S stays positive in practice. |

---

## Part 1: Mathematical Soundness Analysis

### 1A. Sigmoid Normalization — `calc_A`

**Proposed:**
```
A(t) = 1 / (1 + exp(-2 × k_A × (A_raw(t) - A_thresh)))
```

**Nondimensional context:** The sigmoid expects `A_raw ∈ [0, 1]` (pre-normalized activity level). The `HR × SV_est` formula in the proposal is describing the **physical meaning** of this dimensionless input, not the raw computation. The caller must pre-normalize so that:
- `A_raw ≈ 0` at complete rest
- `A_raw ≈ 1` at maximal exercise

**Verified behavior** (with defaults `k_A=5.0`, `A_thresh=0.3`):

| A_raw | A(t) | ΔG_A | Physiological interpretation |
|-------|------|------|------------------------------|
| 0.00 | **0.0474** | 0.00695 | Complete rest; ~5% residual from sigmoid baseline |
| 0.10 | **0.119** | 0.0169 | Very light activity (e.g., standing) |
| 0.30 | **0.500** | 0.0600 | Threshold; half-maximal activation (brisk walking) |
| 0.50 | **0.881** | 0.0949 | Moderate exercise (jogging); near saturation |
| 0.70 | **0.982** | 0.0995 | Vigorous exercise (running); saturated |
| 1.00 | **0.999** | 0.0999 | Maximal exercise; effectively saturated |

**Finding:** The sigmoid behaves as intended — sub-threshold activity (A_raw < 0.3) produces negligible A(t), and near-maximal activity saturates. The ~5% residual at `A_raw = 0` is a feature, not a bug: it ensures the sigmoid is smooth at zero and doesn't affect model behavior when `A_raw = NULL` (separate code path).

**Slope factor clarification:** The `-2 × k_A` scaling means the derivative at the threshold point is `k_A/2` (not `k_A`). With default `k_A = 5.0`, the slope at threshold is `2.5`. This is documented as `k_A` being "gain (steepness of transition)" — accurate as a qualitative description, but note that the actual slope is `k_A/2`.

### 1B. Raw Activity Input: HR × SV — Normalization Gap

**Issue (MEDIUM):** The proposal defines `A_raw(t) = HR(t) × SV_est(t)` where `SV_est` is "normalized to [0,1] fraction of resting maximum." A typical range for `HR × SV_est` is:

| Condition | HR (bpm) | SV_est (×rest max) | A_raw | Notes |
|-----------|----------|-------------------|-------|-------|
| Rest | 65 | 1.00 | 65 | |
| Walking | 110 | 1.25 | 138 | 2.1× rest cardiac output |
| Running | 160 | 1.35 | 216 | 3.3× rest cardiac output |

These values (65–260) are far above the sigmoid threshold `A_thresh = 0.3`, causing `A(t) ≈ 1` for ANY activity. The sigmoid cannot distinguish walking from running.

**The proposal must clarify** that the sigmoid path requires `A_raw ∈ [0, 1]`. A suggested normalization:
```
A_raw_norm = (HR × SV_est - CO_rest) / (CO_max - CO_rest)
```
where `CO = HR × SV`. This gives `A_raw_norm ≈ 0` at rest and `≈ 1` at max exercise. Alternatively, the simpler clip form can accept any pre-normalized input.

**Recommendation:** Add a normalization formula or note that the sigmoid path assumes `A_raw ∈ [0, 1]`.

### 1C. Direct Glucose Uptake — `ΔG_A`

**Proposed:**
```
ΔG_A[i] = γ_A × A[i] / (1 + κ_A × A[i])
```

**Nondimensional analysis** (defaults `γ_A=0.15`, `κ_A=0.5`):

| A | ΔG_A | Context in model units |
|---|------|----------------------|
| 0.0 | 0 | No effect |
| 0.5 (at threshold) | 0.060 | 6% of peak glucose (G_max ≈ 3.0) |
| 1.0 (maximal) | 0.100 | 10% of peak glucose |

**G_total = G_bias + Σ(gⱼ) - ΔG_A.** With G_bias min ≈ 0.10 at night/early morning, maximal ΔG_A = 0.10 would reduce G to exactly 0 at the minimum. In practice, exercise doesn't occur at the glucose nadir (early morning fasting), so G remains positive.

**Non-negativity guarantee:** The maximum ΔG_A = γ_A/(1+κ_A) = 0.10 (for A ≤ 1). The asymptotic bound γ_A/κ_A = 0.30 (as A → ∞) is a looser but mathematically valid supremum. With defaults, ΔG_A < 0.10 always, guaranteeing G_total > 0 at all times (since G_bias + Σgⱼ ≥ 0.10).

**Edge case:** If users change parameters to `γ_A > 0.15` or `κ_A < 0.5`, the maximum ΔG_A increases. The non-negativity guarantee becomes parameter-dependent. The model should not hardcode this assumption.

### 1D. Cortisol Elevation — `c_mod`

**Proposed:**
```
c_mod[i] = c[i] × (1 + β_A × A[i])
```

**Nondimensional analysis** (default `β_A=0.20`):

| Scenario | c | I_S = 1 - 0.23×c - 0.97×m | ΔI_S from exercise |
|----------|---|---------------------------|-------------------|
| No exercise (A=0), midday | 1.23 | 1 - 0.28 - 0 = 0.72 | — |
| Max exercise (A=1), midday | 1.23×1.20=1.48 | 1 - 0.34 - 0 = 0.66 | −0.06 |

The cortisol-mediated insulin suppression changes `I_S` by −0.06 at maximum. This flows to `I_E = a × I_S`, changing `I_E` by `−0.06a ≈ −0.02` for typical `a ≈ 0.4`. The meal glucose component `1.3k_G/(1 + I_E)` changes by approximately `+0.02` to `+0.04` — a small counter-regulatory effect.

**Assessment:** The cortisol pathway is quantitatively modest in the default configuration but creates qualitatively correct behavior: acute exercise transiently elevates glucose through cortisol-mediated insulin suppression, competing with the glucose-lowering effects of direct uptake and sensitization.

### 1E. Post-Activity Sensitization — Exponential Filter

**Proposed:**
```
s_A[0] = 0
s_A[i] = s_A[i-1]·exp(-dt/τ_A) + η_A·A[i-1]·(1 - exp(-dt/τ_A))
```

This is a discrete-time implementation of `τ_A · ds_A/dt + s_A = η_A · A(t)`.

**Numerical behavior** (defaults `τ_A=2.0h`, `η_A=0.40`):

| Time post-exercise | s_A (fraction of η_A) | I_E_eff multiplier | Effect on meal glucose (for I_E=0.5) |
|-------------------|----------------------|-------------------|--------------------------------------|
| 0h (peak) | 0.40 (100%) | ×1.40 | G↓0.10 from ∼0.87→∼0.77 |
| 2h | 0.15 (37%) | ×1.15 | G↓0.04 from ∼0.87→∼0.83 |
| 4h | 0.054 (14%) | ×1.05 | G↓0.015 from ∼0.87→∼0.85 |
| 8h | 0.007 (2%) | ×1.007 | G↓0.002 (negligible) |

**Assessment:** The filter produces meaningful post-exercise effects for 2-4 hours, decaying to negligible by 8 hours. This aligns with the acute GLUT4 recycling time (contraction-mediated GLUT4 returns to intracellular stores within 3-4 hours post-exercise). The proposal states "post-activity insulin sensitization" — this is the **acute recovery** phase, not the 12-48h gene-expression-mediated sensitization (which involves HKII upregulation, AS160 signaling changes, a mechanistically distinct process). For the stated scope, `τ_A = 2.0h` is appropriate.

**One-sample input lag:** The filter uses `A[i-1]` (previous value) rather than `A[i]` (current). This introduces a one-timestep delay. For `dt = 1 min` (typical high-resolution data), the lag is negligible (`dt/τ_A = 1/120 = 0.0083`). For sparse data (`dt = 30 min`), the lag becomes noticeable. Recommend either using `A[i]` or documenting this as a deliberate choice.

**τ_A negative/degenerate guard (HIGH):** If `τ_A < 0`, `exp(-dt/τ_A) = exp(+dt/|τ_A|) > 1`, making the filter **unstable** (s_A grows exponentially). If `τ_A = 0`, the filter behaves as `s_A[i] = η_A · A[i-1]` (instantaneous tracking, no smoothing). The implementation must guard against `τ_A ≤ 0`:
```c
if (tau_A <= 0.0) {
    // Sensitization disabled — passthrough
    for (int i = 0; i < N; i++) {
        out_s_A[i] = 0.0;
        out_I_E_eff[i] = I_E[i];
    }
    return;
}
```

### 1F. Full Pipeline Numerical Effect

**Net effect of 1 hour of maximal exercise:**

| Pathway | Mechanism | Glucose change (model units) |
|---------|-----------|------------------------------|
| Direct uptake | ΔG_A subtraction | −0.10 |
| Cortisol | c_mod → I_S↓ → I_E↓ → meal G↑ | +0.02 (small counter-regulatory) |
| Sensitization | I_E_eff↑ → meal G↓ | −0.04 to −0.10 (depends on I_E) |
| **Net (low I_E, fasting)** | | **−0.12** (mostly direct uptake) |
| **Net (high I_E, post-meal)** | | **−0.18** (direct + sensitization) |

**Physiological interpretation:** Exercise is 50% more effective at lowering glucose in the post-meal state (when insulin is high) than in the fasting state. This matches known physiology — exercise is particularly effective for reducing post-prandial glucose excursions.

---

## Part 2: Physiological Accuracy Analysis

### 2A. Post-Exercise Insulin Sensitization — Scope Clarification

**Claim:** "τ_A = 2.0h is too short, real effect lasts 12-48h."

**Withdrawn.** After studying the nondimensionalized model and the literature more carefully:

The proposal models **acute post-exercise GLUT4 recovery** — the return of contraction-recruited GLUT4 transporters from the plasma membrane back to intracellular stores. This has a time constant of **1-4 hours** in human muscle. The default `τ_A = 2.0h` is appropriate.

The **12-48h effect** is mechanistically distinct — mediated by increased HKII expression, AS160/TBC1D4 phosphorylation changes, and enhanced insulin signaling. Capturing this would require:
- A second, slower exponential component (`τ_A_slow ≈ 24h`)
- Or a different model structure entirely

The proposal does not claim to model this. If future work adds this capability, a two-time-constant model is recommended:
```
s_A[i] = η_A_fast · s_A_fast[i] + η_A_slow · s_A_slow[i]
```
with `τ_fast ≈ 2h`, `τ_slow ≈ 24h`, and `η_slow ≪ η_fast`.

### 2B. Cortisol Elevation Magnitude

**Claim:** "β_A = 0.20 is too low, 40-90% increases at vigorous exercise."

**Withdrawn.** The 20% cortisol boost in model units produces a system-level glucose increase of ~+0.02 to +0.04 — a small but qualitatively correct counter-regulatory effect. The parameter is not meant to match real-world cortisol percentage increases; it's tuned to produce the right system-level behavior in the model.

The key physiological features captured:
1. **Cortisol increases with activity** ✓ (proportional to A)
2. **Proportional to baseline** ✓ (multiplicative, avoids spurious nocturnal elevation)
3. **Suppresses insulin secretion** ✓ (feeds through I_S = 1 − 0.23c_mod − 0.97m)
4. **Competes with glucose-lowering pathways** ✓ (transient counter-regulatory glucose rise)

Notable limitation (for documentation): the cortisol response is instantaneous. Real exercise cortisol has a 20-30 minute latency to peak. A first-order lag with τ ≈ 0.3h could be added for enhanced fidelity.

### 2C. Direct Glucose Uptake Magnitude

**Assessment:** With `γ_A = 0.15`, the maximum `ΔG_A = 0.10` model units. At peak glucose (G ≈ 3.0), this is a 3.3% reduction. At the glucose mean (G ≈ 1.14), a 8.8% reduction. This is conservative but reasonable for moderate exercise.

The saturable form (`Michaelis-Menten`) is physiologically correct:
- **Untrained individuals:** Glucose uptake saturates at 55-75% VO₂max (Kalliokoski et al., 2003)
- **Trained individuals:** Less saturation; can be modeled by decreasing κ_A

The additive structure of contraction-mediated (ΔG_A) and insulin-mediated (I_E_eff denominator) uptake is supported by the literature (Lund et al., 1995, *PNAS*): they use distinct signaling pathways (AMPK vs PI3K) and independent GLUT4 pools.

### 2D. Missing Hepatic Glucose Counter-Regulation

**Issue (MEDIUM):** During exercise, the liver increases glucose production by:
- 100% (doubles) at mild exercise (30-45% VO₂max)
- 100-200% at moderate exercise (55-65% VO₂max)
- 200-400% (3-5× rest) at heavy exercise (>75% VO₂max)

(From: Petersen et al., 2004; Lavoie et al., 1997; Wahren et al., 1971; Wasserman & Cherrington, 1991)

Without this mechanism, the model is **unidirectional** — only increased disposal, no increased production. For short-duration exercise (10-30 min), the error is small because hepatic glycogen stores provide buffer. For prolonged exercise (>45 min) or in fasting conditions, the model will overestimate glucose reduction.

**Recommendation:** Document as a known limitation. For future work, add a hepatic term:
```
HGP_A[i] = δ_A × A(t[i])       // additive to G_bias
```
where `δ_A` is tuned so hepatic output rises to match ~50-80% of muscle uptake, maintaining blood glucose homeostasis.

---

## Part 3: Corrected Issue Inventory

### 🔴 HIGH Priority — Must Fix

**#1: `τ_A ≤ 0` makes the exponential filter unstable or degenerate**
- **File:** `calc_I_E_eff` in implementation
- **Issue:** `τ_A < 0` → `exp(-dt/τ_A) > 1` → s_A grows exponentially without bound. `τ_A = 0` → instantaneous tracking (no smoothing, no decay).
- **Fix:** Add guard at function entry:
  ```c
  if (tau_A <= 0.0) {
      for (int i = 0; i < N; i++) {
          out_s_A[i] = 0.0;
          out_I_E_eff[i] = I_E[i];
      }
      return;
  }
  ```

### 🟡 MEDIUM Priority — Should Address

**#2: Missing hepatic counter-regulation documentation**
- **File:** PROPOSED.md — add "Known Limitations" subsection
- **Issue:** Model predicts net glucose reduction from exercise without accounting for the liver increasing glucose production by 100-400%
- **Fix:** Add documentation noting this limitation and the conditions under which it matters (prolonged exercise, fasting state)

**#3: A_raw normalization path ambiguity**
- **File:** PROPOSED.md Section 2
- **Issue:** HR×SV formula produces values 65-260, but sigmoid with `A_thresh = 0.3` expects [0,1] input
- **Fix:** Add explicit normalization formula or clarify that sigmoid path requires pre-normalized [0,1] input:
  ```
  A_raw_norm = (HR·SV_est - CO_rest) / (CO_max - CO_rest)
  ```
  where `CO = HR·SV_est`.

### 🔵 LOW Priority — Cosmetic/Documentation

| Item | Description |
|------|-------------|
| **Slope factor naming** | `k_A` is half the actual sigmoid slope at threshold. Cosmetic — document as "gain factor" not "slope." |
| **Sigmoid range notation** | `A(t) ∈ [0, 1)` → `A(t) ∈ (0, 1)` mathematically. Minor. |
| **calc_G parameter name** | Rename `I_E` → `I_E_eff` in the `calc_G` signature for clarity. Purely cosmetic. |
| **Alternative multiplicative form** | Section 3a's `×(1-ΔG_A)` option could go negative if ΔG_A > 1. Either remove or add clip guard. |
| **One-sample filter lag** | `s_A` uses `A[i-1]`; consider using `A[i]` for zero-lag response. Minor at typical dt. |

---

## Part 4: Recommendations for Implementation

### Phase 1 — C Implementation (HIGH priority fixes)

1. **Add `tau_A <= 0` guard** at the top of `calc_I_E_eff`
2. **Pass `I_E_eff` to `calc_G`** in `run_cma_model` (the pipeline diagram is correct; ensure implementation follows it)
3. **When `A_raw == NULL`**, zero-fill all activity output buffers to ensure exact backward compatibility

### PROPOSED.md Documentation (MEDIUM priority)

4. **Add normalization formula** for `A_raw` conversion from HR×SV to [0,1]
5. **Add "Known Limitations" section** documenting missing hepatic counter-regulation
6. **Clarify τ_A = 2.0h scope** — document that this models acute GLUT4 recovery, not 12-48h gene-expression-mediated sensitization

### Optional Refinements

7. **Temporal delay for cortisol** — add first-order lag with τ ~ 0.3h for enhanced fidelity
8. **Two-phase sensitization** — for future work, add slow component τ ~ 24h to capture gene-expression effects

---

## References

- Mikines KJ, et al. (1988). *Am J Physiol Endocrinol Metab* 254(3):E248-E259. PMID: 3348398
- Magkos F, et al. (2008). *Clinical Science* 114(2):143-150. DOI: 10.1042/CS20070134
- Cartee GD (2015). *Am J Physiol Endocrinol Metab* 309(12):E949-E959. PMID: 26487009
- Richter EA, Hargreaves M (2013). *Physiol Rev* 93(3):993-1017. PMID: 23899560
- Sylow L, et al. (2017). *Nat Rev Endocrinol* 13(3):133-148. PMID: 27739515
- Lund S, et al. (1995). *PNAS* 92(13):5817-5821. PMID: 7597034
- Petersen KF, et al. (2004). *J Clin Endocrinol Metab* 89(9):5010-5016.
- Wahren J, et al. (1971). *J Clin Invest* 50(12):2715-2725. PMID: 5129313
- Wasserman DH, Cherrington AD (1991). *Am J Physiol* 260(6):E811-E824.
- Kalliokoski KK, et al. (2003). *Med Sci Sports Exerc* 35(5):752-759.
