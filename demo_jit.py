"""
demo_jit.py — Validation and benchmarks for the JIT-compiled CMA engine.

Compares three execution engines for the CMA model:

1. ``.so`` shared library (``pfun_cma_engine.pfun_cma_engine``)
2. MCJIT JIT compiler  (``pfun_cma_engine.jit_engine``)
3. ORC JIT compiler    (``pfun_cma_engine.orc_jit_engine``)

All three are loaded best-effort with graceful fallback if any engine is
unavailable.  The script verifies numerically identical output across
available engines and reports wall-clock speed-ups.
"""

__docformat__ = "restructuredtext"

import logging
import time
import sys

import numpy as np

# Suppress noisy debug output from llvmlite before any other imports.
logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Reference (.so) — best-effort load
# ---------------------------------------------------------------------------
try:
    import pfun_cma_engine.pfun_cma_engine as _so_engine

    _SO_AVAILABLE = True
except Exception:
    _SO_AVAILABLE = False


# ---------------------------------------------------------------------------
# MCJIT — best-effort load
# ---------------------------------------------------------------------------
try:
    from pfun_cma_engine.jit_engine import jit_run_cma_engine_c  # noqa: E402

    _MCJIT_AVAILABLE = True
except Exception:
    _MCJIT_AVAILABLE = False


# ---------------------------------------------------------------------------
# ORC JIT — best-effort load
# ---------------------------------------------------------------------------
try:
    from pfun_cma_engine.orc_jit_engine import (  # noqa: E402
        orc_jit_run_cma_engine_c,
    )

    _ORC_AVAILABLE = True
except Exception:
    _ORC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_reference(
    t: np.ndarray,
    d: float,
    taup: float,
    taug_val: float,
    taug_vec: np.ndarray | None,
    B: float,
    Cm: float,
    toff: float,
    tM: np.ndarray,
    seed: int | None,
    eps: float,
) -> dict[str, np.ndarray]:
    """Call the ``.so``-based ``run_cma_engine_c`` and return the result dict.

    Parameters
    ----------
    t : ndarray, shape (N,)
        Time vector.
    d : float
    taup : float
    taug_val : float
    taug_vec : ndarray or None
    B : float
    Cm : float
    toff : float
    tM : ndarray, shape (n_meals,)
    seed : int or None
    eps : float

    Returns
    -------
    dict with keys ``G``, ``g``, ``I_E``, ``L``, ``m``.
    """
    return _so_engine.run_cma_engine_c(
        t=t,
        d=d,
        taup=taup,
        taug_val=taug_val,
        taug_vec=taug_vec,
        B=B,
        Cm=Cm,
        toff=toff,
        tM=tM,
        seed=seed,
        eps=eps,
    )


def run_mcjit(
    t: np.ndarray,
    d: float,
    taup: float,
    taug_val: float,
    taug_vec: np.ndarray | None,
    B: float,
    Cm: float,
    toff: float,
    tM: np.ndarray,
    seed: int | None,
    eps: float,
) -> dict[str, np.ndarray]:
    """Call the MCJIT convenience wrapper and return the result dict.

    Parameters
    ----------
    t : ndarray, shape (N,)
    d : float
    taup : float
    taug_val : float
    taug_vec : ndarray or None
    B : float
    Cm : float
    toff : float
    tM : ndarray, shape (n_meals,)
    seed : int or None
    eps : float

    Returns
    -------
    dict with keys ``G``, ``g``, ``I_E``, ``L``, ``m``.
    """
    return jit_run_cma_engine_c(
        t=t,
        d=d,
        taup=taup,
        taug_val=taug_val,
        taug_vec=taug_vec,
        B=B,
        Cm=Cm,
        toff=toff,
        tM=tM,
        seed=seed,
        eps=eps,
    )


def run_orc(
    t: np.ndarray,
    d: float,
    taup: float,
    taug_val: float,
    taug_vec: np.ndarray | None,
    B: float,
    Cm: float,
    toff: float,
    tM: np.ndarray,
    seed: int | None,
    eps: float,
) -> dict[str, np.ndarray]:
    """Call the ORC JIT convenience wrapper and return the result dict.

    Parameters
    ----------
    t : ndarray, shape (N,)
    d : float
    taup : float
    taug_val : float
    taug_vec : ndarray or None
    B : float
    Cm : float
    toff : float
    tM : ndarray, shape (n_meals,)
    seed : int or None
    eps : float

    Returns
    -------
    dict with keys ``G``, ``g``, ``I_E``, ``L``, ``m``.
    """
    return orc_jit_run_cma_engine_c(
        t=t,
        d=d,
        taup=taup,
        taug_val=taug_val,
        taug_vec=taug_vec,
        B=B,
        Cm=Cm,
        toff=toff,
        tM=tM,
        seed=seed,
        eps=eps,
    )


def compare_results(
    a: dict[str, np.ndarray],
    b: dict[str, np.ndarray],
    atol: float = 1e-12,
) -> tuple[bool, dict[str, tuple[bool, float]]]:
    """Compare all five output arrays between two result dicts.

    Parameters
    ----------
    a : dict
        Result from one engine.
    b : dict
        Result from another engine.
    atol : float
        Absolute tolerance for ``np.allclose``.

    Returns
    -------
    (all_match, details)
        ``all_match`` is ``True`` iff every key matches within *atol*.
        ``details`` maps each key to ``(match: bool, max_abs_diff: float)``.
    """
    keys = ["G", "g", "I_E", "L", "m"]
    details: dict[str, tuple[bool, float]] = {}

    for key in keys:
        a_arr = a[key]
        b_arr = b[key]
        match = np.allclose(a_arr, b_arr, atol=atol)
        max_diff = float(np.max(np.abs(a_arr - b_arr)))
        details[key] = (match, max_diff)

    all_match = all(m for m, _ in details.values())
    return all_match, details


def benchmark(
    fn,  # callable[[...], dict]
    kwargs: dict,
    iterations: int = 5,
) -> tuple[float, float, list[float]]:
    """Time *fn(**kwargs)* over *iterations* runs.

    Returns
    -------
    (mean_seconds, std_seconds, all_times)
    """
    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn(**kwargs)
        times.append(time.perf_counter() - t0)

    mean_sec = float(np.mean(times))
    std_sec = float(np.std(times, ddof=1)) if len(times) > 1 else 0.0
    return mean_sec, std_sec, times


def benchmark_warm(
    engine_fn,  # callable: engine.run_cma_engine_c_jit(...)
    kwargs: dict,
    iterations: int = 100,
) -> tuple[float, float, list[float]]:
    """Time *engine_fn(**kwargs)* over *iterations* runs, excluding compilation.

    Unlike :func:`benchmark`, this function expects a pre-constructed engine's
    bound method so that the one-time JIT compilation cost is not measured.

    Returns
    -------
    (mean_seconds, std_seconds, all_times)
    """
    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        engine_fn(**kwargs)
        times.append(time.perf_counter() - t0)

    mean_sec = float(np.mean(times))
    std_sec = float(np.std(times, ddof=1)) if len(times) > 1 else 0.0
    return mean_sec, std_sec, times


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Define test parameters matching the C model's expected domain.
    t = np.linspace(0, 24, 97)  # 15-min intervals over 24h
    d = 1.0
    taup = 1.2
    taug_val = 1.0
    taug_vec = None  # use NULL
    B = 0.05
    Cm = 0.0
    toff = 0.0
    tM = np.array([7.0, 11.0, 17.5])  # breakfast, lunch, dinner
    seed = 42
    eps = 1e-18

    print("=" * 60)
    print("PFun CMA Engine \u2014 Multi-Engine Validation & Benchmark")
    print("=" * 60)

    kwargs = dict(
        t=t,
        d=d,
        taup=taup,
        taug_val=taug_val,
        taug_vec=taug_vec,
        B=B,
        Cm=Cm,
        toff=toff,
        tM=tM,
        seed=seed,
        eps=eps,
    )

    # --- Step 1: Run .so reference (if available) ----------------------------
    ref = None
    t_ref = float("nan")
    if not _SO_AVAILABLE:
        print("\n[1/5] Running .so reference...")
        print("      SKIPPED \u2014 .so library could not be loaded.")
    else:
        print("\n[1/5] Running .so reference...")
        t0 = time.perf_counter()
        try:
            ref = run_reference(
                t, d, taup, taug_val, taug_vec, B, Cm, toff, tM, seed, eps,
            )
            t_ref = time.perf_counter() - t0
            print(f"      Done in {t_ref * 1000:.2f} ms")
        except Exception as exc:
            ref = None
            print(f"      ERROR: .so engine failed: {exc}")

    # --- Step 2: Run MCJIT (if available) -----------------------------------
    mcjit = None
    t_mcjit = float("nan")
    if not _MCJIT_AVAILABLE:
        print("\n[2/5] Running MCJIT...")
        print("      SKIPPED \u2014 MCJIT engine could not be loaded.")
    else:
        print("\n[2/5] Running MCJIT...")
        t0 = time.perf_counter()
        try:
            mcjit = run_mcjit(
                t, d, taup, taug_val, taug_vec, B, Cm, toff, tM, seed, eps,
            )
            t_mcjit = time.perf_counter() - t0
            print(f"      Done in {t_mcjit * 1000:.2f} ms")
        except Exception as exc:
            mcjit = None
            print(f"      ERROR: MCJIT engine failed: {exc}")

    # --- Step 3: Run ORC JIT (if available) ---------------------------------
    orc = None
    t_orc = float("nan")
    if not _ORC_AVAILABLE:
        print("\n[3/5] Running ORC JIT...")
        print("      SKIPPED \u2014 ORC JIT engine could not be loaded.")
    else:
        print("\n[3/5] Running ORC JIT...")
        t0 = time.perf_counter()
        try:
            orc = run_orc(
                t, d, taup, taug_val, taug_vec, B, Cm, toff, tM, seed, eps,
            )
            t_orc = time.perf_counter() - t0
            print(f"      Done in {t_orc * 1000:.2f} ms")
        except Exception as exc:
            orc = None
            print(f"      ERROR: ORC JIT engine failed: {exc}")

    # --- Step 4: Cross-engine comparison ------------------------------------
    print("\n[4/5] Cross-engine comparison...")

    pairs: list[tuple[str, dict | None, str, dict | None]] = []

    if ref is not None and mcjit is not None:
        pairs.append((".so", ref, "MCJIT", mcjit))
    if ref is not None and orc is not None:
        pairs.append((".so", ref, "ORC", orc))
    if mcjit is not None and orc is not None:
        pairs.append(("MCJIT", mcjit, "ORC", orc))

    if not pairs:
        print("      No engines available for comparison.")
    else:
        all_ok = True
        for name_a, res_a, name_b, res_b in pairs:
            match, details = compare_results(res_a, res_b, atol=1e-12)
            label = f"{name_a:7s} vs {name_b:7s}:"
            status = "\u2713 PASS" if match else "\u2717 FAIL"
            print(f"      {label} {status}")
            for key, (m, max_diff) in details.items():
                inner = "\u2713" if m else "\u2717"
                print(
                    f"                      {inner}  "
                    f"{key:5s}  max|diff| = {max_diff:.2e}"
                )
            if not match:
                all_ok = False

        if all_ok:
            print("\n      \u2713 ALL ENGINES PRODUCE IDENTICAL OUTPUTS")
        else:
            print("\n      \u2717 OUTPUT MISMATCH DETECTED")
            sys.exit(1)

    # --- Step 5: Benchmark --------------------------------------------------
    print("\n[5/5] Benchmark (5 iterations each)...")

    # Collect benchmark results; each entry is (name, mean_sec, std_sec).
    bench_results: list[tuple[str, float | None, float | None]] = []

    if _SO_AVAILABLE:
        so_mean, so_std, _ = benchmark(run_reference, kwargs)
        bench_results.append((".so", so_mean, so_std))
        print(f"      .so:     {so_mean * 1000:.2f} \u00b1 {so_std * 1000:.2f} ms")
    else:
        bench_results.append((".so", None, None))
        print("      .so:     (skipped \u2014 library not available)")

    if _MCJIT_AVAILABLE:
        mcjit_mean, mcjit_std, _ = benchmark(run_mcjit, kwargs)
        bench_results.append(("MCJIT", mcjit_mean, mcjit_std))
        print(
            f"      MCJIT:   {mcjit_mean * 1000:.2f} \u00b1 "
            f"{mcjit_std * 1000:.2f} ms"
        )
    else:
        bench_results.append(("MCJIT", None, None))
        print("      MCJIT:   (skipped \u2014 engine not available)")

    if _ORC_AVAILABLE:
        orc_mean, orc_std, _ = benchmark(run_orc, kwargs)
        bench_results.append(("ORC", orc_mean, orc_std))
        print(
            f"      ORC:     {orc_mean * 1000:.2f} \u00b1 "
            f"{orc_std * 1000:.2f} ms"
        )
    else:
        bench_results.append(("ORC", None, None))
        print("      ORC:     (skipped \u2014 engine not available)")

    # Speedup summary vs .so
    so_entry = next(
        (e for e in bench_results if e[0] == ".so" and e[1] is not None),
        None,
    )
    if so_entry is not None and so_entry[1] > 0:
        so_mean_val = so_entry[1]
        speedups: list[str] = []
        for name, mean, _ in bench_results:
            if name != ".so" and mean is not None and mean > 0:
                ratio = so_mean_val / mean
                speedups.append(f"{name}: {ratio:.2f}x")
        if speedups:
            print(f"\n      Speedups vs .so:  {', '.join(speedups)}")

    # --- Step 6: Warm-run benchmark -----------------------------------------
    print("\n[6/6] Warm-run benchmark (100 iterations, exclude compilation)...")

    # Look up cold-run numbers from Step 5 for comparison.
    def _cold_mean(name: str) -> float | None:
        return next(
            (e[1] for e in bench_results if e[0] == name and e[1] is not None),
            None,
        )

    cold_mcjit = _cold_mean("MCJIT")
    cold_orc = _cold_mean("ORC")

    if _MCJIT_AVAILABLE:
        from pfun_cma_engine.jit_engine import JITEngine

        mcjit_engine = JITEngine()
        w_mcjit_mean, w_mcjit_std, _ = benchmark_warm(
            mcjit_engine.run_cma_engine_c_jit, kwargs, iterations=100
        )
        mcjit_cold_str = (
            f"{cold_mcjit * 1000:.2f} ms"
            if cold_mcjit is not None
            else "N/A"
        )
        print(
            f"      MCJIT:   {w_mcjit_mean * 1000:.2f} \u00b1 "
            f"{w_mcjit_std * 1000:.2f} ms per call "
            f"(cold: {mcjit_cold_str})"
        )
        mcjit_engine.close()

    if _ORC_AVAILABLE:
        from pfun_cma_engine.orc_jit_engine import ORCJITEngine

        orc_engine = ORCJITEngine()
        w_orc_mean, w_orc_std, _ = benchmark_warm(
            orc_engine.run_cma_engine_c_jit, kwargs, iterations=100
        )
        orc_cold_str = (
            f"{cold_orc * 1000:.2f} ms"
            if cold_orc is not None
            else "N/A"
        )
        print(
            f"      ORC:     {w_orc_mean * 1000:.2f} \u00b1 "
            f"{w_orc_std * 1000:.2f} ms per call "
            f"(cold: {orc_cold_str})"
        )
        orc_engine.close()

    # --- Check for critical failure -----------------------------------------
    engines_ran = sum(1 for e in bench_results if e[1] is not None)
    if engines_ran == 0:
        sys.exit(2)

    print("\n" + "=" * 60)
    print("Validation complete.")
    print("=" * 60)
