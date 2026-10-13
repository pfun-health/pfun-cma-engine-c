"""Measure model error after quantizing API inputs and outputs."""

import argparse
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pfun_cma_engine.pfun_cma_engine import run_cma_engine_c

FP32_SCALED_TOLERANCE = 1e-6
FP16_FAILURE_THRESHOLD = 1e-4
SIGNALS = (
    "G",
    "g",
    "I_E",
    "I_E_eff",
    "L",
    "m",
    "c",
    "c_mod",
    "A",
    "s_A",
    "a",
    "I_S",
)


def scenarios():
    """Return deterministic baseline and activity/stress input scenarios."""
    baseline_t = np.linspace(0.0, 24.0, 193)
    activity_t = np.linspace(0.0, 48.0, 385)
    return {
        "baseline": {
            "t": baseline_t,
            "d": 0.0,
            "taup": 0.5,
            "taug_val": 4.0,
            "tM": np.array([7.0, 11.0, 17.5]),
            "B": 0.05,
            "Cm": 0.0,
            "toff": 0.0,
            "A_raw": None,
            "seed": None,
            "eps": 1e-18,
            "k_A": 5.0,
            "A_thresh": 0.3,
            "gamma_A": 0.15,
            "kappa_A": 0.5,
            "beta_A": 0.2,
            "eta_A": 0.4,
            "tau_A": 2.0,
        },
        "activity_stress": {
            "t": activity_t,
            "d": 0.2,
            "taup": 0.7,
            "taug_val": 3.5,
            "tM": np.array([6.75, 12.0, 20.5]),
            "B": 0.08,
            "Cm": 0.3,
            "toff": 0.25,
            "A_raw": np.clip(np.sin(2.0 * np.pi * activity_t / 24.0), 0.0, 1.0),
            "gamma_A": 0.2,
            "k_A": 5.0,
            "A_thresh": 0.3,
            "kappa_A": 0.5,
            "eta_A": 0.6,
            "tau_A": 4.0,
            "beta_A": 0.2,
        },
    }


def _quantized_inputs(kwargs, dtype):
    quantized = {}
    for name, value in kwargs.items():
        if isinstance(value, np.ndarray):
            quantized[name] = value.astype(dtype).astype(np.float64)
        elif isinstance(value, (float, int)):
            quantized[name] = dtype(value).item()
        else:
            quantized[name] = value
    return quantized


def analyze_precision():
    """Compare FP32/FP16 input and output round-trips with the FP64 engine."""
    cases = {}
    for scenario_name, kwargs in scenarios().items():
        reference = run_cma_engine_c(**kwargs)
        for precision, dtype in (("FP32", np.float32), ("FP16", np.float16)):
            actual = run_cma_engine_c(**_quantized_inputs(kwargs, dtype))
            for signal in SIGNALS:
                rounded = actual[signal].astype(dtype).astype(np.float64)
                error = np.abs(rounded - reference[signal])
                scale = max(1.0, float(np.max(np.abs(reference[signal]))))
                scaled_error = float(np.max(error)) / scale
                key = (precision, signal)
                row = {
                    "scenario": scenario_name,
                    "max_abs_error": float(np.max(error)),
                    "max_scaled_error": scaled_error,
                }
                if key not in cases or scaled_error > cases[key]["max_scaled_error"]:
                    cases[key] = row

    summary = {}
    for precision in ("FP32", "FP16"):
        rows = [row for (candidate, _), row in cases.items() if candidate == precision]
        worst = max(rows, key=lambda row: row["max_scaled_error"])
        summary[precision] = {
            "max_scaled_error": worst["max_scaled_error"],
            "max_abs_error": worst["max_abs_error"],
            "scenario": worst["scenario"],
        }
    return cases, summary


def render_report(cases, summary):
    fp32_passes = summary["FP32"]["max_scaled_error"] <= FP32_SCALED_TOLERANCE
    fp16_fails = summary["FP16"]["max_scaled_error"] > FP16_FAILURE_THRESHOLD
    lines = [
        "# CMA Engine Precision Assessment",
        "",
        "## Result",
        "",
        "| Boundary representation | Worst scaled absolute error | Worst-case scenario | Assessment |",
        "|---|---:|---|---|",
        (
            f"| FP32 | {summary['FP32']['max_scaled_error']:.3e} "
            f"| {summary['FP32']['scenario']} "
            f"| {'Pass' if fp32_passes else 'Exceeds tolerance'} "
            f"(limit {FP32_SCALED_TOLERANCE:.0e}) |"
        ),
        (
            f"| FP16 | {summary['FP16']['max_scaled_error']:.3e} "
            f"| {summary['FP16']['scenario']} "
            f"| {'Fails' if fp16_fails else 'Within failure threshold'} "
            f"(failure threshold {FP16_FAILURE_THRESHOLD:.0e}) |"
        ),
        "",
        "Scaled absolute error is `max(abs(candidate - FP64 reference)) / "
        "max(1, max(abs(FP64 reference)))` for the signal and scenario.",
        "FP32 is accepted here at a scaled error of at most `1e-6`; FP16 is "
        "considered inadequate when any measured signal exceeds `1e-4`.",
        "",
        "## Per-signal worst cases",
        "",
        "| Precision | Signal | Scenario | Max absolute error | Max scaled absolute error |",
        "|---|---|---|---:|---:|",
    ]
    for precision in ("FP32", "FP16"):
        for signal in SIGNALS:
            row = cases[(precision, signal)]
            lines.append(
                f"| {precision} | `{signal}` | {row['scenario']} "
                f"| {row['max_abs_error']:.3e} | {row['max_scaled_error']:.3e} |"
            )

    lines.extend(
        [
            "",
            "## Method and scope",
            "",
            "- The reference is the current C engine, which evaluates its model "
            "using `double` values.",
            "- At each candidate boundary, every numeric model input (including "
            "time arrays and parameters) is rounded to the indicated IEEE format, "
            "then widened to `double` for the existing engine call. Every output "
            "is rounded to that format before comparison.",
            "- Scenarios cover a 24-hour baseline at 193 points and a 48-hour "
            "activity/stress case at 385 points. The model calls are deterministic "
            "and use no random seed.",
            "- This measures input/output storage and transport precision; it does "
            "not emulate lower-precision arithmetic inside the model. Thus it "
            "supports FP32 boundary use under the stated error budget, rejects "
            "FP16 for that budget, and does not establish that internal FP32 "
            "arithmetic is safe.",
            "- The error budget is a numerical engineering criterion, not a claim "
            "about physiological or clinical accuracy.",
            "",
            "Regenerate with `make precision-report`. Acceptance checks run with "
            "`make test-precision`.",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs" / "PRECISION.md",
        help="Markdown report output path",
    )
    args = parser.parse_args()
    cases, summary = analyze_precision()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(cases, summary), encoding="utf-8")
    print(f"Wrote precision report to {args.output}")
    for precision in ("FP32", "FP16"):
        print(
            f"{precision}: max scaled absolute error "
            f"{summary[precision]['max_scaled_error']:.3e}"
        )


if __name__ == "__main__":
    main()
