# PROPOSED: Activity Function Extension for the CMA Model

## 1. Motivation

The current CMA model captures circadian and meal-driven glucose dynamics but lacks a physiologically essential dimension: **physical activity**. Skeletal muscle contractions during activity drive insulin-independent glucose uptake (via GLUT4 translocation), elevate cortisol, and increase post-exercise insulin sensitivity. Adding an activity pathway makes the model useful for exercise physiology, recovery tracking, and real-world glucose forecasting under varying activity levels.

## 2. Activity Input Definition

**Raw input:**
```
A_raw(t) = HR(t) × SV_est(t)
```
where `HR(t)` is heart rate (bpm) and `SV_est(t)` is estimated stroke volume (normalized to `[0,1]` fraction of resting maximum).

**Normalized activity signal:**
```
A(t) = sigmoid( k_A × (A_raw(t) - A_thresh) )
     = 1 / ( 1 + exp( -2 × k_A × (A_raw(t) - A_thresh) ) )
```
- `k_A` — gain (steepness of transition), default `5.0`
- `A_thresh` — activation threshold, default `0.3`
- `A(t) ∈ [0, 1)` with sigmoid smoothness

If `A_raw` is already pre-normalized to `[0,1]`, the simpler form `A(t) = clip(A_raw(t), 0, 1)` may be used, but the sigmoid is recommended for physiological realism (sub-threshold activity produces negligible effect; near-maximal activity saturates).

### New Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `k_A` | double | 5.0 | Activity sigmoid gain |
| `A_thresh` | double | 0.3 | Activity activation threshold |
| `γ_A` | double | 0.15 | Direct glucose uptake coefficient (insulin-independent) |
| `κ_A` | double | 0.5 | Glucose uptake saturation constant |
| `β_A` | double | 0.20 | Activity cortisol amplification factor |
| `η_A` | double | 0.40 | Post-activity insulin sensitization magnitude |
| `τ_A` | double | 2.0 | Insulin sensitization decay time constant (hours) |

---

## 3. The Activity Function: Three Integration Points

### 3a. Direct Insulin-Independent Glucose Uptake (contraction-mediated)

This is the primary effect. Active skeletal muscle consumes glucose via GLUT4 translocation independently of insulin.

```
ΔG_A[i] = γ_A × A(t[i]) / ( 1 + κ_A × A(t[i]) )
```

The saturation form `A / (1 + κ_A × A)` ensures diminishing returns at high intensity, matching known physiology.

**Affects `calc_G` (line 109 of `pfun_cma_engine.c`):**

The original total glucose:
```
G_total[i] = G_bias[i] + Σⱼ gⱼ[i]
```

becomes:
```
G_total[i] = G_bias[i] + Σⱼ gⱼ[i] - ΔG_A[i]
```

Alternatively, the activity term can be incorporated as a multiplicative reduction of the meal glucose component:
```
G_total[i] = G_bias[i] + Σⱼ gⱼ[i] × ( 1 - ΔG_A[i] )
```
if exercise specifically suppresses post-prandial glucose excursions.

### 3b. Activity-Modulated Cortisol Elevation

Acute exercise elevates cortisol, which feeds into the existing cortisol → insulin → glucose cascade. This creates realistic coupling: activity raises cortisol → suppresses insulin secretion → transiently elevates glucose, competing with the direct glucose uptake.

```
c_mod[i] = c_baseline[i] × ( 1 + β_A × A(t[i]) )
```

This replaces the raw `c[i]` downstream in `calc_I_S` (line 97). The form keeps cortisol non-negative and scales proportionally to baseline circadian cortisol, avoiding spurious elevation during periods when cortisol is naturally low.

### 3c. Post-Activity Insulin Sensitization (time-convolved)

After activity, tissue remains more insulin-sensitive for several hours. This is modeled as a time convolution with an exponential kernel, implemented efficiently as a recursive filter:

```
s_A[0] = 0
s_A[i] = s_A[i-1] × exp(-dt / τ_A) + η_A × A(t[i-1]) × (1 - exp(-dt / τ_A))
```

where `dt = t[i] - t[i-1]` and `s_A[i] ∈ [0, η_A)`.

Effective extracellular insulin:
```
I_E_eff[i] = I_E[i] × ( 1 + s_A[i] )
```

The multiplicative form `1 + s_A[i]` makes it a *sensitization* (always ≥ 1) that decays back to baseline after activity ceases.

---

## 4. Modified Model Pipeline

```
t (time vector)
│
├── calc_L  ──►  L (Light)
│                  │
├── calc_M  ──►  m (Melatonin)     [unchanged]
│              │
├── calc_c  ──►  c (Cortisol)
│              │
│   ★ NEW: c_mod[i] = c[i] × (1 + β_A × A(t[i]))   [activity-elevated cortisol]
│              │
├── calc_A  ──►  A(t) activity signal               [★ NEW intermediate]
│   (from HR×SV_est input, via sigmoid)
│              │
├── calc_I_S──►  I_S = 1 - 0.23×c_mod - 0.97×m     [uses modified cortisol]
│              │
├── calc_I_E──►  I_E = a × I_S                      [unchanged]
│              │
│   ★ NEW: I_E_eff[i] = I_E[i] × (1 + s_A[i])       [post-activity sensitization]
│              │
└── calc_G  ──►  G = G_bias + Σ gⱼ - ΔG_A          [subtract contraction-mediated uptake]
```

New intermediate signals added:
- `A(t)` — normalized activity signal (size N)
- `c_mod(t)` — activity-modified cortisol (size N, replaces `c` downstream)
- `I_E_eff(t)` — activity-sensitized extracellular insulin (size N, replaces `I_E` in glucose calculation)
- `s_A(t)` — post-activity sensitivity state (size N, internal to sensitization filter)

---

## 5. Updated `calc_G` with Activity

The modified glucose equation in full form:

```
G_bias[i] = B × (1 + meal_distr_pfun(Cm, t[i], toff))

ΔG_A[i] = γ_A × A(t[i]) / (1 + κ_A × A(t[i]))

G_total[i] = G_bias[i]
           + Σⱼ[ 1.3 × K_pfun((t[i] - tmⱼ) / taugⱼ²) / (1 + I_E_eff[i]) ]
           - ΔG_A[i]
```

All terms keep `G_total[i] ≥ 0` for physiological validity (`ΔG_A[i] < G_bias[i] + Σgⱼ[i]` must hold for all inputs; the saturation term guarantees this since `γ_A / κ_A ≤ 0.3` by default).

---

## 6. API Changes

### C API (`pfun_cma_engine.h`)

New signal functions:
```c
void calc_A(const double* t, int N, const double* A_raw,
            double k_A, double A_thresh, double* out_A);

void calc_c_mod(int N, const double* c, const double* A,
                double beta_A, double* out_c_mod);

void calc_I_E_eff(int N, const double* I_E, const double* A,
                  const double* t, double eta_A, double tau_A,
                  double* out_I_E_eff, double* out_s_A);
```

Modified `calc_G` signature adds `A` and `gamma_A`, `kappa_A` parameters:
```c
void calc_G(const double* t, int N, const double* I_E,
            const double* A,              // ★ NEW
            const double* tM, int n_meals,
            const double* taug, double B, double Cm, double toff,
            double gamma_A, double kappa_A,  // ★ NEW
            int include_bias_in_components,
            double* out_G_instant, double* out_g_components);
```

Updated `run_cma_model` signature adds:
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

New output buffers (pre-allocated by caller): `out_c_mod`, `out_A`, `out_I_E_eff`, `out_s_A`.

### Python API (`pfun_cma_engine.py`)

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
):
```

Returns:
```python
return {
    "G": out_G,
    "g": out_g.reshape((n_meals, N)),
    "I_E": out_I_E,
    "I_E_eff": out_I_E_eff,   # ★ NEW
    "L": out_L,
    "m": out_m,
    "c_mod": out_c_mod,       # ★ NEW
    "A": out_A,                # ★ NEW
    "s_A": out_s_A,            # ★ NEW
}
```

When `A_raw` is `None`, activity effects are disabled (all downstream activity terms evaluate to zero), preserving exact backward compatibility.

---

## 7. Implementation Plan

### Phase 1 — Core C Implementation

1. Add `calc_A()` — normalize raw HR×SV to `[0,1)` via sigmoid
2. Add `calc_c_mod()` — cortisol amplification: `c_mod = c × (1 + β_A × A)`
3. Add `calc_I_E_eff()` — time-convolved post-activity sensitization (recursive exponential filter)
4. Modify `calc_G()` — accept new activity parameters and subtract `ΔG_A` from total glucose
5. Update `run_cma_model()` — orchestrate new intermediate calculations in correct order:
   ```
   calc_L → calc_M → calc_c → calc_A → calc_c_mod → calc_a → calc_I_S → calc_I_E → calc_I_E_eff → calc_G
   ```

### Phase 2 — Python Wrapper Update

6. Add activity parameters to `run_cma_engine_c()` with defaults that disable activity when `A_raw=None`
7. Add new output buffers (`out_c_mod`, `out_A`, `out_I_E_eff`, `out_s_A`)
8. Include new signals in returned dictionary (including `c_mod`, `A`, `I_E_eff`, `s_A`)

### Phase 3 — Validation

9. Verify backward compatibility: `A_raw=None` produces identical output to current model
10. Verify monotonicity: increasing `A_raw` strictly decreases total glucose and increases cortisol
11. Verify saturation: at `A(t)=1`, glucose reduction saturates at `γ_A / (1 + κ_A)`
12. Verify decay: post-activity insulin sensitivity returns to baseline within `~4×τ_A` hours

---

## 8. Edge Cases and Mathematical Guarantees

| Condition | Behavior | Guarantee |
|-----------|----------|-----------|
| `A_raw(t) = 0` ∀t | All activity terms vanish; model reduces to original | Exact backward compatibility |
| `A_raw(t) = 1` (maximal) | Maximum glucose reduction `γ_A/(1+κ_A)`, max cortisol `× (1+β_A)`, max sensitization `×(1+η_A)` | `G(t) ≥ max(0, G_original - 0.3)` with defaults |
| `A_thresh = 0`, `k_A → ∞` | Step function: binary on/off at `A_raw > 0` | Discontinuous; sigmoid recommended |
| `τ_A = 0` | Post-activity sensitization instantaneously tracks `A(t)` | Degenerate; use `τ_A > dt` |
| `β_A = 0` | No cortisol amplification | Cortisol and downstream insulin unchanged |
| `η_A = 0` | No post-activity sensitization | Only direct glucose uptake `ΔG_A` active |
| `γ_A = 0`, `η_A = 0` | No activity-glucose coupling | Only cortisol pathway active |

All activity parameters default to zero-equivalent behavior when `A_raw` is `NULL`/`None` — no code changes needed for existing callers.
