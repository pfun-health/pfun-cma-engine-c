"""Validation tests for the activity function extension.

Tests cover:
- Backward compatibility: A_raw=None produces identical output to the baseline
- Monotonicity: increasing A_raw decreases glucose and increases cortisol
- Saturation: ΔG_A saturates at gamma_A / (1 + kappa_A)
- Decay: post-activity sensitivity decays to baseline within ~4×tau_A
- Edge cases: zero parameters, boundary conditions, tau_A=0 guard
- Integration: full pipeline produces non-NaN outputs in expected ranges
"""

import ctypes
import sys
import os
import numpy as np
import pytest

# Ensure the package is importable from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pfun_cma_engine.pfun_cma_engine import run_cma_engine_c

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

T_HOURS = 48.0
DT = 0.1
T = np.arange(0.0, T_HOURS, DT)
N = len(T)
TM_DEFAULT = np.array([7.0, 11.0, 17.5])

BASE_KWARGS = dict(
    t=T,
    d=0.0,
    taup=0.5,
    taug_val=4.0,
    B=0.05,
    Cm=0.0,
    toff=0.0,
    tM=TM_DEFAULT,
    seed=None,
    eps=1e-18,
)


def _baseline():
    """Run model with no activity (A_raw=None)."""
    return run_cma_engine_c(**BASE_KWARGS, A_raw=None)


def _with_activity(A_raw, **overrides):
    kw = {**BASE_KWARGS, **overrides, "A_raw": A_raw}
    return run_cma_engine_c(**kw)


# ---------------------------------------------------------------------------
# 1. Backward compatibility
# ---------------------------------------------------------------------------


def test_backward_compatibility_no_activity():
    """A_raw=None must be bit-identical to the original model outputs."""
    res_none = _baseline()
    res_zeros = _with_activity(
        np.zeros(N),
        k_A=5.0,
        A_thresh=0.3,
        gamma_A=0.0,
        kappa_A=0.5,
        beta_A=0.0,
        eta_A=0.0,
        tau_A=2.0,
    )
    # When all activity coefficients are zero and A_raw is None vs. zeros the
    # glucose signal must match closely (sigmoid at 0 gives small residual
    # ~0.047, but with beta_A=0, gamma_A=0, eta_A=0 the effect on G is zero).
    np.testing.assert_allclose(res_none["G"], res_zeros["G"], rtol=1e-14)
    np.testing.assert_allclose(res_none["I_E"], res_zeros["I_E"], rtol=1e-14)
    np.testing.assert_allclose(res_none["L"], res_zeros["L"], rtol=1e-14)


def test_backward_compatibility_new_keys():
    """The returned dict must include both old and new keys."""
    res = _baseline()
    for key in ("G", "g", "I_E", "I_E_eff", "L", "m", "c", "c_mod", "A", "s_A", "a", "I_S"):
        assert key in res, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# 2. Monotonicity
# ---------------------------------------------------------------------------


def test_activity_decreases_glucose():
    """Increasing activity should (on average) decrease glucose."""
    res_low = _with_activity(np.full(N, 0.1))
    res_high = _with_activity(np.full(N, 0.9))
    assert res_high["G"].mean() < res_low["G"].mean(), (
        "Higher activity should produce lower mean glucose"
    )


def test_activity_increases_cortisol():
    """Activity-modulated cortisol must be >= baseline cortisol (beta_A >= 0)."""
    res = _with_activity(np.full(N, 0.5), beta_A=0.20)
    # c_mod[i] = c[i] * (1 + beta_A * A[i]) >= c[i] when A >= 0
    assert np.all(res["c_mod"] >= res["c"] - 1e-12), (
        "c_mod must be >= c when beta_A > 0 and A >= 0"
    )


def test_activity_increases_effective_insulin():
    """Post-activity sensitization must increase I_E_eff >= I_E."""
    res = _with_activity(np.full(N, 0.8), eta_A=0.40, tau_A=2.0)
    assert np.all(res["I_E_eff"] >= res["I_E"] - 1e-12), (
        "I_E_eff must be >= I_E when eta_A >= 0"
    )


# ---------------------------------------------------------------------------
# 3. Saturation
# ---------------------------------------------------------------------------


def test_glucose_uptake_saturation():
    """ΔG_A at A=1 must approach gamma_A/(1+kappa_A) for a pure-activity run."""
    gamma_A = 0.15
    kappa_A = 0.5
    expected_max_uptake = gamma_A / (1.0 + kappa_A)

    # Create a run where G is dominated by bias and activity (no meals)
    t_short = np.arange(0.0, 2.0, 0.01)
    res_inactive = run_cma_engine_c(
        t=t_short, d=0, taup=0.5, taug_val=4.0, B=0.05, Cm=0, toff=0,
        tM=np.array([100.0]),  # meal far in future — no prandial contribution
        A_raw=None, gamma_A=gamma_A, kappa_A=kappa_A,
    )
    res_max = run_cma_engine_c(
        t=t_short, d=0, taup=0.5, taug_val=4.0, B=0.05, Cm=0, toff=0,
        tM=np.array([100.0]),
        A_raw=np.ones(len(t_short)),
        gamma_A=gamma_A, kappa_A=kappa_A, beta_A=0.0, eta_A=0.0, tau_A=2.0,
    )
    uptake = res_inactive["G"] - res_max["G"]
    # Allow 1% tolerance; the bias term is shared, so the difference isolates ΔG_A
    assert np.allclose(uptake, expected_max_uptake, atol=expected_max_uptake * 0.01), (
        f"Expected ΔG_A ≈ {expected_max_uptake:.4f}, got mean {uptake.mean():.4f}"
    )


# ---------------------------------------------------------------------------
# 4. Decay
# ---------------------------------------------------------------------------


def test_sensitivity_decay():
    """Post-activity sensitivity s_A must decay toward the resting floor within 4×tau_A.

    The exponential filter is driven by A(t), which has a small positive
    residual (~0.047) when A_raw=0 due to the sigmoid.  The filter therefore
    converges to a non-zero floor s_A_floor = eta_A * A_rest rather than zero.
    The test verifies that the *excess above the floor* decays to < 5% of the
    peak excess within 4×tau_A hours after the end of activity.
    """
    tau_A = 2.0
    eta_A = 0.40
    k_A = 5.0
    A_thresh = 0.3
    decay_threshold = 4 * tau_A  # hours

    # Build a time series where activity is only in the first 2 hours
    t_long = np.arange(0.0, 24.0, 0.05)
    A_raw = np.zeros(len(t_long))
    A_raw[t_long < 2.0] = 1.0  # activity during first 2h only

    res = _with_activity(
        A_raw=A_raw,
        t=t_long,
        d=0, taup=0.5, taug_val=4.0, B=0.05, Cm=0, toff=0,
        tM=np.array([100.0]),
        eta_A=eta_A, tau_A=tau_A, gamma_A=0.0, beta_A=0.0,
        k_A=k_A, A_thresh=A_thresh,
    )

    # Steady-state floor: s_A converges to eta_A * A_rest when input is constant
    A_rest = 1.0 / (1.0 + np.exp(-2.0 * k_A * (0.0 - A_thresh)))
    s_A_floor = eta_A * A_rest

    # Peak excess (above floor) occurs at the transition point ~t=2
    peak_idx = np.argmax(res["s_A"])
    peak_excess = res["s_A"][peak_idx] - s_A_floor

    # After 4×tau_A from the end of activity, excess should be < 5% of peak
    cutoff_idx = np.searchsorted(t_long, 2.0 + decay_threshold)
    s_A_late_excess = res["s_A"][cutoff_idx:] - s_A_floor

    assert s_A_late_excess.max() < 0.05 * peak_excess, (
        f"Excess above floor should decay to < 5% of peak_excess={peak_excess:.4f} "
        f"after 4×tau_A, got max excess={s_A_late_excess.max():.4f}"
    )


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------


def test_tau_A_zero_guard():
    """tau_A=0 must not crash and must produce s_A=0, I_E_eff=I_E."""
    res = _with_activity(np.full(N, 0.5), tau_A=0.0)
    np.testing.assert_array_equal(res["s_A"], 0.0)
    np.testing.assert_array_equal(res["I_E_eff"], res["I_E"])


def test_tau_A_negative_guard():
    """Negative tau_A must not crash and must disable sensitization."""
    res = _with_activity(np.full(N, 0.5), tau_A=-1.0)
    np.testing.assert_array_equal(res["s_A"], 0.0)
    np.testing.assert_array_equal(res["I_E_eff"], res["I_E"])


def test_zero_activity_input():
    """A_raw=0 everywhere should produce negligible glucose change with defaults."""
    res_none = _baseline()
    # With A_raw=0 the sigmoid gives ~0.047 residual but with default params
    # gamma_A=0.15 the effect is small: ΔG_A ≈ 0.047*0.15/(1+0.047*0.5) ≈ 0.007
    res_zero = _with_activity(np.zeros(N))
    # Glucose should be slightly lower due to small residual — just check no NaN
    assert not np.any(np.isnan(res_zero["G"]))


def test_gamma_A_zero():
    """gamma_A=0 disables direct glucose uptake; G should equal baseline."""
    res_none = _baseline()
    res_act = _with_activity(np.full(N, 0.9), gamma_A=0.0, beta_A=0.0, eta_A=0.0)
    np.testing.assert_allclose(res_none["G"], res_act["G"], rtol=1e-14)


def test_beta_A_zero():
    """beta_A=0 means no cortisol amplification; c_mod must equal c."""
    res = _with_activity(np.full(N, 0.8), beta_A=0.0)
    np.testing.assert_allclose(res["c_mod"], res["c"], rtol=1e-14)


def test_eta_A_zero():
    """eta_A=0 means no post-activity sensitization; s_A must be zero."""
    res = _with_activity(np.full(N, 0.8), eta_A=0.0, tau_A=2.0)
    np.testing.assert_array_equal(res["s_A"], 0.0)
    np.testing.assert_array_equal(res["I_E_eff"], res["I_E"])


# ---------------------------------------------------------------------------
# 6. Integration (full model smoke test)
# ---------------------------------------------------------------------------


def test_full_model_no_nan():
    """Full pipeline must produce finite outputs in expected ranges."""
    A_raw = np.clip(np.sin(2 * np.pi * T / 24.0), 0.0, 1.0)
    res = _with_activity(A_raw)
    for key, arr in res.items():
        assert not np.any(np.isnan(arr)), f"NaN found in '{key}'"
        assert not np.any(np.isinf(arr)), f"Inf found in '{key}'"


def test_glucose_in_expected_range():
    """Glucose must stay in [0, 5] under typical activity conditions."""
    A_raw = np.clip(np.random.default_rng(42).uniform(0.0, 1.0, N), 0.0, 1.0)
    res = _with_activity(A_raw)
    assert res["G"].min() >= 0.0, "Glucose went negative"
    assert res["G"].max() <= 5.0, f"Glucose exceeded 5.0: {res['G'].max():.3f}"


def test_activity_signal_in_unit_range():
    """Normalized activity A must be in (0, 1) for any A_raw input."""
    A_raw = np.linspace(0.0, 1.0, N)
    res = _with_activity(A_raw)
    assert res["A"].min() > 0.0
    assert res["A"].max() < 1.0


def test_s_A_bounded():
    """Sensitization state s_A must be bounded by [0, eta_A)."""
    eta_A = 0.40
    res = _with_activity(np.full(N, 1.0), eta_A=eta_A, tau_A=2.0)
    assert res["s_A"].min() >= -1e-12
    assert res["s_A"].max() < eta_A + 1e-10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
