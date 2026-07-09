#!/usr/bin/env python3
"""
benchmark-compare.py — Comprehensive benchmark comparison tool for pfun-cma-engine-c

This script benchmarks three execution engines across different build configurations
and scenarios:

1. `.so` shared library (reference implementation)
2. MCJIT JIT compiler
3. ORC JIT compiler

Scenarios tested:
- Cold start: First run including JIT compilation overhead
- Warm runs: Multiple iterations with JIT compilation amortized
- Varying time point counts: small (13), medium (97), large (193)

Generates a markdown report with:
- Executive summary
- Build configurations
- Performance tables
- Comparison matrix
- Recommendations
"""

__version__ = "1.0.0"
__docformat__ = "restructuredtext"

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

# Configure logging before any imports that might use it
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress noisy debug output from llvmlite and other verbose libraries
logging.getLogger("llvmlite").setLevel(logging.WARNING)
logging.getLogger("cffi").setLevel(logging.WARNING)

# ─────────────────────────────────────────────────────────────────────────────
# Engine loading with graceful fallback
# ─────────────────────────────────────────────────────────────────────────────

_SO_AVAILABLE = False
_MCJIT_AVAILABLE = False
_ORC_AVAILABLE = False

try:
    import pfun_cma_engine.pfun_cma_engine as _so_engine
    _SO_AVAILABLE = True
except Exception as e:
    logger.debug(f".so engine unavailable: {e}")

try:
    from pfun_cma_engine.jit_engine import jit_run_cma_engine_c, JITEngine
    _MCJIT_AVAILABLE = True
except Exception as e:
    logger.debug(f"MCJIT engine unavailable: {e}")

try:
    from pfun_cma_engine.orc_jit_engine import (
        orc_jit_run_cma_engine_c,
        ORCJITEngine,
    )
    _ORC_AVAILABLE = True
except Exception as e:
    logger.debug(f"ORC JIT engine unavailable: {e}")


# Validate that at least one engine is available
if not (_SO_AVAILABLE or _MCJIT_AVAILABLE or _ORC_AVAILABLE):
    logger.error(
        "FATAL: No benchmark engines available. Please ensure the following are installed:\n"
        "  - pfun_cma_engine (for .so baseline)\n"
        "  - pfun_cma_engine[jit] (for MCJIT support)\n"
        "  - pfun_cma_engine[orc] (for ORC JIT support)\n"
        "See the project README for installation instructions."
    )
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class TimingStats:
    """Statistics for a single timing measurement."""

    mean_ms: float
    """Mean execution time in milliseconds."""
    std_ms: float
    """Standard deviation in milliseconds."""
    min_ms: float
    """Minimum execution time in milliseconds."""
    max_ms: float
    """Maximum execution time in milliseconds."""
    count: int
    """Number of iterations."""
    all_times_ms: list[float] = field(default_factory=list)
    """All individual timing measurements in milliseconds."""

    def relative_to(self, baseline: "TimingStats") -> float:
        """Compute speedup ratio relative to baseline."""
        if baseline.mean_ms == 0:
            return 1.0
        return baseline.mean_ms / self.mean_ms

    def variance_high(self, threshold: float = 0.5) -> bool:
        """Check if standard deviation is unusually high (coefficient of variation)."""
        if self.mean_ms == 0:
            return False
        cv = self.std_ms / self.mean_ms
        return cv > threshold


@dataclass
class BenchmarkResult:
    """Results for one engine/scenario combination."""

    engine: str
    """Engine name: '.so', 'MCJIT', 'ORC'."""
    scenario: str
    """Scenario: 'cold', 'warm-13', 'warm-97', 'warm-193'."""
    build: str
    """Build type: 'release', 'debug', 'lto'."""
    timing: TimingStats | None = None
    """Timing statistics, or None if engine/scenario unavailable."""
    error: str | None = None
    """Error message if benchmark failed."""


@dataclass
class BuildConfig:
    """Configuration for a single build variant."""

    name: str
    """Display name: 'Release', 'Debug', 'LTO'."""
    make_target: str
    """Make target to invoke: 'all', 'debug', 'lto-test'."""
    cflags: str
    """Expected CFLAGS in build output."""
    enabled: bool = True
    """Whether this build should be run."""


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Functions (mirroring demo_jit.py)
# ─────────────────────────────────────────────────────────────────────────────


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
    """Call the `.so`-based engine."""
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
    """Call the MCJIT engine."""
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
    """Call the ORC JIT engine."""
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


def benchmark(
    fn: Callable[..., dict[str, np.ndarray]],
    kwargs: dict[str, Any],
    iterations: int = 5,
) -> tuple[float, float, float, float, list[float]]:
    """
    Time *fn(**kwargs)* over *iterations* runs.

    Parameters
    ----------
    fn : callable
        Function to benchmark.
    kwargs : dict
        Keyword arguments to pass to fn.
    iterations : int
        Number of iterations to run.

    Returns
    -------
    (mean_seconds, std_seconds, min_seconds, max_seconds, all_times)
        All times in milliseconds; all_times is list in milliseconds for logging.
    """
    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn(**kwargs)
        times.append(time.perf_counter() - t0)

    times_np = np.array(times)
    mean_sec = float(np.mean(times_np))
    std_sec = float(np.std(times_np, ddof=0)) if len(times) > 1 else 0.0
    min_sec = float(np.min(times_np))
    max_sec = float(np.max(times_np))
    times_ms = [t * 1000 for t in times]

    return mean_sec, std_sec, min_sec, max_sec, times_ms


def benchmark_warm(
    engine_fn: Callable[..., dict[str, np.ndarray]],
    kwargs: dict[str, Any],
    iterations: int = 100,
) -> tuple[float, float, float, float, list[float]]:
    """
    Time *engine_fn(**kwargs)* over *iterations* warm runs.

    This assumes the engine is already constructed and JIT-compiled.
    We time only the execution, not the compilation.

    Parameters
    ----------
    engine_fn : callable
        Pre-constructed engine method.
    kwargs : dict
        Keyword arguments to pass to engine_fn.
    iterations : int
        Number of iterations to run.

    Returns
    -------
    (mean_milliseconds, std_milliseconds, min_milliseconds, max_milliseconds, all_times_ms)
        All return values are in milliseconds.
    """
    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        engine_fn(**kwargs)
        times.append(time.perf_counter() - t0)

    times_np = np.array(times)
    mean_sec = float(np.mean(times_np))
    std_sec = float(np.std(times_np, ddof=0)) if len(times) > 1 else 0.0
    min_sec = float(np.min(times_np))
    max_sec = float(np.max(times_np))
    times_ms = [t * 1000 for t in times]

    return mean_sec, std_sec, min_sec, max_sec, times_ms


# ─────────────────────────────────────────────────────────────────────────────
# Build Management
# ─────────────────────────────────────────────────────────────────────────────


def build_library(build_target: str, project_root: Path) -> tuple[bool, str]:
    """
    Run make to build the library.

    Parameters
    ----------
    build_target : str
        Make target: 'all', 'debug', 'lto-test', etc.
    project_root : Path
        Root directory of the project.

    Returns
    -------
    (success: bool, message: str)
    """
    # Validate build_target to prevent command injection
    allowed_targets = ["all", "debug", "lto-test"]
    if build_target not in allowed_targets:
        msg = f"Invalid build target '{build_target}'. Allowed: {allowed_targets}"
        logger.error(msg)
        raise ValueError(msg)

    logger.info(f"Building with target: {build_target}")
    try:
        result = subprocess.run(
            ["make", build_target],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            logger.info(f"Build {build_target} succeeded")
            return True, f"Build target '{build_target}' succeeded"
        else:
            error_msg = result.stderr or result.stdout
            logger.error(f"Build {build_target} failed:\n{error_msg}")
            return False, f"Build failed: {error_msg[:200]}"
    except subprocess.TimeoutExpired:
        msg = f"Build timed out after 120s"
        logger.error(msg)
        return False, msg
    except Exception as e:
        msg = f"Build error: {e}"
        logger.error(msg)
        return False, msg


def verify_build(project_root: Path) -> bool:
    """
    Verify that the shared library was built.

    Parameters
    ----------
    project_root : Path
        Root directory of the project.

    Returns
    -------
    bool
        True if the .so file exists and is reasonably recent.
    """
    so_path = project_root / "pfun_cma_engine" / "libpfun_cma_engine.so"
    if so_path.exists():
        mtime = so_path.stat().st_mtime
        now = time.time()
        age_sec = now - mtime
        if age_sec < 300:  # Built within last 5 minutes
            logger.info(f"Verified .so exists: {so_path}")
            return True
        else:
            logger.warning(f".so exists but is {age_sec:.0f}s old")
            return False
    else:
        logger.warning(f".so not found at {so_path}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Orchestration
# ─────────────────────────────────────────────────────────────────────────────


def benchmark_scenario(
    engine_name: str,
    engine_fn,
    warm_engine_fn=None,
    num_points: int = 97,
    iterations_cold: int = 5,
    iterations_warm: int = 100,
) -> dict[str, TimingStats | None]:
    """
    Run benchmarks for one engine across cold and warm scenarios.

    Parameters
    ----------
    engine_name : str
        Name of engine: '.so', 'MCJIT', 'ORC'.
    engine_fn : callable
        Function to call for cold run.
    warm_engine_fn : callable, optional
        Function to call for warm runs (may be different object).
    num_points : int
        Number of time points in the t vector.
    iterations_cold : int
        Number of iterations for cold run.
    iterations_warm : int
        Number of iterations for warm run.

    Returns
    -------
    dict
        Keys: 'cold', 'warm'; values: TimingStats or None if error.
    """
    # Standard test parameters
    t = np.linspace(0, 24, num_points)
    d = 1.0
    taup = 1.2
    taug_val = 1.0
    taug_vec = None
    B = 0.05
    Cm = 0.0
    toff = 0.0
    tM = np.array([7.0, 11.0, 17.5])
    seed = 42
    eps = 1e-18

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

    results: dict[str, TimingStats | None] = {}

    # Cold run
    logger.info(f"  Benchmarking {engine_name} cold ({num_points} points)...")
    try:
        mean_s, std_s, min_s, max_s, times_ms = benchmark(
            engine_fn, kwargs, iterations=iterations_cold
        )
        results["cold"] = TimingStats(
            mean_ms=mean_s * 1000,
            std_ms=std_s * 1000,
            min_ms=min_s * 1000,
            max_ms=max_s * 1000,
            count=iterations_cold,
            all_times_ms=times_ms,
        )
        logger.info(
            f"    Cold: {results['cold'].mean_ms:.2f} ± {results['cold'].std_ms:.2f} ms"
        )
    except Exception as e:
        logger.error(f"    Cold run failed: {e}")
        results["cold"] = None

    # Warm run (only if warm_engine_fn provided)
    if warm_engine_fn is not None:
        logger.info(f"  Benchmarking {engine_name} warm ({num_points} points)...")
        try:
            mean_s, std_s, min_s, max_s, times_ms = benchmark_warm(
                warm_engine_fn, kwargs, iterations=iterations_warm
            )
            results["warm"] = TimingStats(
                mean_ms=mean_s * 1000,
                std_ms=std_s * 1000,
                min_ms=min_s * 1000,
                max_ms=max_s * 1000,
                count=iterations_warm,
                all_times_ms=times_ms,
            )
            logger.info(
                f"    Warm: {results['warm'].mean_ms:.2f} ± {results['warm'].std_ms:.2f} ms"
            )
        except Exception as e:
            logger.error(f"    Warm run failed: {e}")
            results["warm"] = None
    else:
        results["warm"] = None

    return results


def run_all_benchmarks(
    project_root: Path,
    build_config: dict[str, str],
) -> list[BenchmarkResult]:
    """
    Run all benchmarks across all engines and scenarios.

    Parameters
    ----------
    project_root : Path
        Root of the project.
    build_config : dict
        Info about the build (e.g., {'name': 'Release', 'cflags': '-O2'}).

    Returns
    -------
    list[BenchmarkResult]
        All benchmark results.
    """
    results: list[BenchmarkResult] = []

    # Define scenarios: (scenario_name, num_points)
    scenarios = [
        ("cold-13", 13),
        ("cold-97", 97),
        ("cold-193", 193),
        ("warm-13", 13),
        ("warm-97", 97),
        ("warm-193", 193),
    ]

    # --- .so baseline
    if _SO_AVAILABLE:
        logger.info("Benchmarking .so baseline...")
        for scenario_name, num_points in scenarios:
            if "cold" in scenario_name:
                bench_res = benchmark_scenario(
                    ".so", run_reference, num_points=num_points
                )
                if bench_res["cold"]:
                    results.append(
                        BenchmarkResult(
                            engine=".so",
                            scenario=scenario_name,
                            build=build_config.get("name", "unknown"),
                            timing=bench_res["cold"],
                        )
                    )
    else:
        logger.warning(".so engine not available")

    # --- MCJIT
    if _MCJIT_AVAILABLE:
        logger.info("Benchmarking MCJIT...")
        for scenario_name, num_points in scenarios:
            if "cold" in scenario_name:
                bench_res = benchmark_scenario(
                    "MCJIT", run_mcjit, num_points=num_points
                )
                if bench_res["cold"]:
                    results.append(
                        BenchmarkResult(
                            engine="MCJIT",
                            scenario=scenario_name,
                            build=build_config.get("name", "unknown"),
                            timing=bench_res["cold"],
                        )
                     )
            else:  # warm
                engine = None
                try:
                    engine = JITEngine()
                    bench_res = benchmark_scenario(
                        "MCJIT",
                        run_mcjit,
                        warm_engine_fn=engine.run_cma_engine_c_jit,
                        num_points=num_points,
                    )
                    if bench_res["warm"]:
                        results.append(
                            BenchmarkResult(
                                engine="MCJIT",
                                scenario=scenario_name,
                                build=build_config.get("name", "unknown"),
                                timing=bench_res["warm"],
                            )
                        )
                except Exception as e:
                    logger.error(f"MCJIT warm run error: {e}")
                finally:
                    if engine is not None:
                        engine.close()
    else:
        logger.warning("MCJIT engine not available")

    # --- ORC JIT
    if _ORC_AVAILABLE:
        logger.info("Benchmarking ORC JIT...")
        for scenario_name, num_points in scenarios:
            if "cold" in scenario_name:
                bench_res = benchmark_scenario(
                    "ORC", run_orc, num_points=num_points
                )
                if bench_res["cold"]:
                    results.append(
                        BenchmarkResult(
                            engine="ORC",
                            scenario=scenario_name,
                            build=build_config.get("name", "unknown"),
                            timing=bench_res["cold"],
                        )
                     )
            else:  # warm
                engine = None
                try:
                    engine = ORCJITEngine()
                    bench_res = benchmark_scenario(
                        "ORC",
                        run_orc,
                        warm_engine_fn=engine.run_cma_engine_c_jit,
                        num_points=num_points,
                    )
                    if bench_res["warm"]:
                        results.append(
                            BenchmarkResult(
                                engine="ORC",
                                scenario=scenario_name,
                                build=build_config.get("name", "unknown"),
                                timing=bench_res["warm"],
                            )
                        )
                except Exception as e:
                    logger.error(f"ORC warm run error: {e}")
                finally:
                    if engine is not None:
                        engine.close()
    else:
        logger.warning("ORC JIT engine not available")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Report Generation
# ─────────────────────────────────────────────────────────────────────────────


def format_timing_stats(stats: TimingStats) -> str:
    """Format timing statistics as a readable string."""
    return (
        f"{stats.mean_ms:.2f} ± {stats.std_ms:.2f} ms "
        f"(min: {stats.min_ms:.2f}, max: {stats.max_ms:.2f})"
    )


def generate_markdown_report(
    results: list[BenchmarkResult],
    builds: list[BuildConfig],
    project_root: Path,
) -> str:
    """
    Generate a comprehensive markdown report.

    Parameters
    ----------
    results : list[BenchmarkResult]
        All benchmark results.
    builds : list[BuildConfig]
        Build configurations that were tested.
    project_root : Path
        Root of the project.

    Returns
    -------
    str
        Markdown report.
    """
    lines: list[str] = []

    # Pre-compute result groupings to avoid O(n²) iterations
    from collections import defaultdict
    results_by_scenario: dict[str, list[BenchmarkResult]] = defaultdict(list)
    results_by_scenario_engine: dict[tuple[str, str], list[BenchmarkResult]] = defaultdict(list)
    
    for result in results:
        if result.timing is not None:
            results_by_scenario[result.scenario].append(result)
            results_by_scenario_engine[(result.scenario, result.engine)].append(result)

    # Header
    lines.append("# Benchmark Comparison Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Project:** pfun-cma-engine-c")
    lines.append(f"**Root:** {project_root}")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        "This report compares three execution engines for the CMA model:"
    )
    lines.append("")
    lines.append("- **`.so` (reference)**: Native shared library, compiled with GCC")
    lines.append("- **MCJIT**: Machine Code JIT compiler via LLVM")
    lines.append("- **ORC JIT**: LLVM ORC (On-Request Compilation) JIT engine")
    lines.append("")

    available_engines = set(r.engine for r in results if r.timing is not None)
    lines.append(f"**Engines tested:** {', '.join(sorted(available_engines))}")
    lines.append("")

    # Test Parameters
    lines.append("### Test Parameters")
    lines.append("")
    lines.append("- **Time domain:** t ∈ [0, 24] hours")
    lines.append("- **Meal times:** 7.0 (breakfast), 11.0 (lunch), 17.5 (dinner)")
    lines.append("- **Glucose decay rate (d):** 1.0")
    lines.append("- **Pancreatic time constant (taup):** 1.2")
    lines.append("- **Seed:** 42 (reproducible random)")
    lines.append("- **Cold iterations:** 5 (includes JIT compilation)")
    lines.append("- **Warm iterations:** 100 (JIT overhead amortized)")
    lines.append("")

    # Build Configurations
    lines.append("## Build Configurations")
    lines.append("")
    for build in builds:
        if build.enabled:
            status = "✅" if build.name in [r.build for r in results] else "⏭️"
            lines.append(f"- {status} **{build.name}**: `make {build.make_target}`")
            lines.append(f"  - CFLAGS: {build.cflags}")
    lines.append("")

    # Group results by scenario
    unique_scenarios = sorted(results_by_scenario.keys())
    unique_engines = sorted(available_engines)

    for scenario in unique_scenarios:
        lines.append(f"## Results: {scenario.replace('-', ' ').title()}")
        lines.append("")

        scenario_results = results_by_scenario[scenario]

        if not scenario_results:
            lines.append("*No data available for this scenario.*")
            lines.append("")
            continue

        # Create a results table
        lines.append("| Engine | Mean (ms) | Std Dev (ms) | Min (ms) | Max (ms) | Count |")
        lines.append("|--------|-----------|--------------|----------|----------|-------|")

        for engine in sorted(set(r.engine for r in scenario_results)):
            engine_results = results_by_scenario_engine[(scenario, engine)]
            if engine_results and engine_results[0].timing:
                t = engine_results[0].timing
                lines.append(
                    f"| {engine:8s} | {t.mean_ms:9.2f} | {t.std_ms:12.2f} | "
                    f"{t.min_ms:8.2f} | {t.max_ms:8.2f} | {t.count:5d} |"
                )

        lines.append("")

        # Speedup vs .so baseline
        so_results = results_by_scenario_engine[(scenario, ".so")]
        so_result = so_results[0] if so_results and so_results[0].timing else None
        
        if so_result and so_result.timing:
            lines.append("### Speedup vs .so Baseline")
            lines.append("")
            lines.append(f"| Engine | Speedup | Factor |")
            lines.append("|--------|---------|--------|")
            baseline = so_result.timing.mean_ms
            for engine in sorted(set(r.engine for r in scenario_results)):
                if engine == ".so":
                    lines.append(f"| {engine:8s} | — | 1.00x |")
                else:
                    engine_results = results_by_scenario_engine[(scenario, engine)]
                    if engine_results and engine_results[0].timing:
                        speedup = baseline / engine_results[0].timing.mean_ms
                        speedup_pct = (speedup - 1.0) * 100
                        if speedup > 1.0:
                            lines.append(
                                f"| {engine:8s} | "
                                f"+{speedup_pct:6.1f}% | {speedup:6.2f}x |"
                            )
                        else:
                            lines.append(
                                f"| {engine:8s} | "
                                f"{speedup_pct:6.1f}% | {speedup:6.2f}x |"
                            )
            lines.append("")

        # Anomaly detection: high variance
        high_var = [
            r for r in scenario_results
            if r.timing and r.timing.variance_high(threshold=0.5)
        ]
        if high_var:
            lines.append("⚠️ **Variance Warning:**")
            for r in high_var:
                cv = r.timing.std_ms / r.timing.mean_ms
                lines.append(
                    f"  - {r.engine}: High variance (CV = {cv:.2%}). "
                    f"Consider more iterations or check for system interference."
                )
            lines.append("")

    # Comparison Matrix
    lines.append("## Comparison Matrix")
    lines.append("")
    lines.append(
        "Speedup factor across all scenarios (values > 1.0 indicate faster than .so):"
    )
    lines.append("")

    # Build matrix
    engines = sorted(available_engines)
    if ".so" in engines:
        engines.remove(".so")
        engines = [".so"] + sorted(engines)

    header_row = "| Scenario |"
    for engine in engines:
        header_row += f" {engine:12s} |"
    lines.append(header_row)

    sep_row = "|----------|"
    for _ in engines:
        sep_row += "----|"
    lines.append(sep_row)

    for scenario in unique_scenarios:
        row = f"| {scenario:8s} |"
        scenario_results = results_by_scenario[scenario]
        so_results = results_by_scenario_engine[(scenario, ".so")]
        so_result = so_results[0] if so_results and so_results[0].timing else None

        for engine in engines:
            eng_results = results_by_scenario_engine[(scenario, engine)]
            eng_result = eng_results[0] if eng_results and eng_results[0].timing else None
            
            if not eng_result or not eng_result.timing:
                row += " — |"
            elif engine == ".so":
                row += " 1.00x |"
            elif so_result and so_result.timing:
                speedup = so_result.timing.mean_ms / eng_result.timing.mean_ms
                row += f" {speedup:6.2f}x |"
            else:
                row += " — |"
        lines.append(row)

    lines.append("")

    # Conclusions and Recommendations
    lines.append("## Conclusions and Recommendations")
    lines.append("")

    if not available_engines:
        lines.append("❌ **No engines available for testing.**")
    else:
        # Find best performer
        all_warm = [
            r for r in results
            if r.timing is not None and "warm" in r.scenario
        ]
        if all_warm:
            best = min(all_warm, key=lambda r: r.timing.mean_ms)
            lines.append(
                f"✅ **Best warm performance:** {best.engine} "
                f"({best.timing.mean_ms:.2f} ms)"
            )
        lines.append("")

        if len(available_engines) > 1:
            lines.append("### Performance Characteristics")
            lines.append("")
            if ".so" in available_engines:
                lines.append(
                    "- The `.so` baseline provides a stable reference. "
                    "Deviations in other engines may indicate JIT overhead."
                )
            if "MCJIT" in available_engines:
                lines.append(
                    "- **MCJIT:** Generally lower compilation overhead than full IR optimization."
                )
            if "ORC" in available_engines:
                lines.append(
                    "- **ORC:** Provides lazy compilation; "
                    "first call slower but amortizes over warm runs."
                )
            lines.append("")

        lines.append("### Recommendations")
        lines.append("")
        lines.append(
            "1. **For latency-critical code:** Prefer warm-run performance metrics."
        )
        lines.append(
            "2. **For scalability:** Monitor cold-start times with large datasets."
        )
        lines.append(
            "3. **Build optimization:** Release builds (-O2) generally recommended; "
            "Debug builds for development only."
        )
        lines.append("")

    # Metadata
    lines.append("---")
    lines.append("")
    lines.append(
        f"*Report generated by `benchmark-compare.py` v{__version__}*"
    )
    lines.append(f"*Generated: {datetime.now().isoformat()}*")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main Orchestration
# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    """
    Main entry point.

    Returns
    -------
    int
        Exit code: 0 for success, 1 for errors.
    """
    project_root = Path(__file__).parent.parent.resolve()
    logger.info(f"Project root: {project_root}")

    # Define build configurations
    builds = [
        BuildConfig(
            name="Release",
            make_target="all",
            cflags="-O2",
            enabled=True,
        ),
        BuildConfig(
            name="Debug",
            make_target="debug",
            cflags="-O0 -g -DDEBUG",
            enabled=True,
        ),
        BuildConfig(
            name="LTO",
            make_target="all",
            cflags="-flto -O2",
            enabled=False,  # LTO may not be available on all systems
        ),
    ]

    logger.info("=" * 70)
    logger.info("pfun-cma-engine-c Benchmark Suite")
    logger.info("=" * 70)

    all_results: list[BenchmarkResult] = []

    # Run benchmarks for each enabled build
    for build in builds:
        if not build.enabled:
            logger.info(f"Skipping {build.name} build (not enabled)")
            continue

        logger.info(f"\n{'=' * 70}")
        logger.info(f"Build: {build.name}")
        logger.info(f"Target: {build.make_target}")
        logger.info(f"{'=' * 70}")

        # Build the library
        success, msg = build_library(build.make_target, project_root)
        if not success:
            logger.warning(f"Build failed: {msg}")
            continue

        # Verify the build
        if not verify_build(project_root):
            logger.warning("Build verification failed")
            continue

        # Run benchmarks
        logger.info(f"Running benchmarks for {build.name} build...")
        build_results = run_all_benchmarks(
            project_root,
            {
                "name": build.name,
                "cflags": build.cflags,
                "target": build.make_target,
            },
        )
        all_results.extend(build_results)

        logger.info(f"Collected {len(build_results)} benchmark results")

    # Generate report
    logger.info("\n" + "=" * 70)
    logger.info("Generating markdown report...")
    logger.info("=" * 70)

    report = generate_markdown_report(all_results, builds, project_root)

    # Save report
    report_path = project_root / "build" / "benchmark_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    logger.info(f"Report saved to: {report_path}")

    # Print report to console
    print("\n" + "=" * 70)
    print(report)
    print("=" * 70)

    return 0 if all_results else 1


if __name__ == "__main__":
    sys.exit(main())
