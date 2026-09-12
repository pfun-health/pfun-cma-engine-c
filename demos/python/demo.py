# coding: utf-8
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pfun_cma_engine import pfun_cma_engine
from scenarios import (
    BASELINE_SCENARIO,
    SCENARIOS,
    ScenarioDefinition,
    build_activity_signal,
    scenario_kwargs,
)

pce = pfun_cma_engine


def print_docstring() -> None:
    print("## Engine docstring\n")
    print(pce.run_cma_engine_c.__doc__)


def compute_as_dataframe(
    defn: ScenarioDefinition, t: np.ndarray
) -> tuple[pd.DataFrame, np.ndarray, dict[str, object]]:
    kwargs = scenario_kwargs(defn, t)
    soln = pce.run_cma_engine_c(**kwargs)
    g = soln.pop("g")
    soln["t"] = t
    df = pd.DataFrame(soln, index=t)
    return df, g, kwargs


def describe_scenario(
    defn: ScenarioDefinition, t: np.ndarray, kwargs: dict[str, object]
) -> None:
    print(f"# {defn.title}\n")
    print(defn.summary)
    print()
    print("## Scenario inputs\n")
    print(f"- meals (h): {list(defn.tM)}")
    print(f"- meal widths taug (h): {list(defn.taug_vec)}")
    print(
        f"- activity pulses (center, width, amplitude): {list(defn.pulses) if defn.pulses else 'none'}"
    )
    if kwargs["A_raw"] is None:
        print("- activity enabled: no")
    else:
        a_raw = kwargs["A_raw"]
        a_norm = build_activity_signal(t, defn.pulses)
        print(f"- activity enabled: yes")
        print(f"- A_raw max: {float(np.max(a_raw)):.3f}")
        print(f"- normalized activity proxy max: {float(np.max(a_norm)):.3f}")
    print(
        "- activity params: "
        f"k_A={defn.k_A}, A_thresh={defn.A_thresh}, gamma_A={defn.gamma_A}, "
        f"kappa_A={defn.kappa_A}, beta_A={defn.beta_A}, eta_A={defn.eta_A}, tau_A={defn.tau_A}"
    )
    print()
    if defn.evidence:
        print("## Physiological rationale\n")
        for idx, item in enumerate(defn.evidence, start=1):
            print(f"{idx}. **{item.label}.** {item.rationale}")
            for source in item.sources:
                print(f"   - {source}")
        print()
    if defn.caveat:
        print("## Scope note\n")
        print(defn.caveat)
        print()


def print_dataframe(df: pd.DataFrame) -> None:
    print("## Tabular output\n")
    print(df.to_markdown())


def plot_timeseries_ascii(
    df: pd.DataFrame, g: np.ndarray, width: int = 60, height: int = 12
) -> None:
    t = df.index.to_numpy(dtype=float)

    def render(series: np.ndarray, title: str, W: int, H: int) -> str:
        vmin, vmax = float(np.min(series)), float(np.max(series))
        span = (vmax - vmin) or 1.0
        tmin, tmax = float(np.min(t)), float(np.max(t))
        tspan = (tmax - tmin) or 1.0
        grid = [[" "] * W for _ in range(H)]
        for tv, vv in zip(t, series):
            col = int(round((tv - tmin) / tspan * (W - 1)))
            row = int(round((1.0 - (vv - vmin) / span) * (H - 1)))
            grid[row][col] = "*"
        lines = [f"{title}  (t: {tmin:g} .. {tmax:g}, value: {vmin:g} .. {vmax:g})"]
        for row in range(H):
            val = vmax - row / (H - 1) * span
            lines.append(f"{val:8.3g} |{''.join(grid[row])}|")
        lines.append(f"{'':8}  +{'-' * W}+")
        xlabels = [f"{tmin + frac * tspan:g}" for frac in (0.0, 0.25, 0.5, 0.75, 1.0)]
        lines.append(f"{'':8}  {''.join(c.center(W // 4) for c in xlabels)}")
        return "\n".join(lines)

    print("## ASCII charts\n")
    for col in df.columns:
        if col == "t":
            continue
        print("```text")
        print(render(df[col].to_numpy(dtype=float), f"{col} vs t", width, height))
        print("```\n")

    markers = "#*+xoO@"
    lines = []
    gmin, gmax = float(np.min(g)), float(np.max(g))
    gspan = (gmax - gmin) or 1.0
    tmin, tmax = float(np.min(t)), float(np.max(t))
    tspan = (tmax - tmin) or 1.0
    W, H = width, height
    grid = [[" "] * W for _ in range(H)]
    for row_idx, meal in enumerate(g):
        marker = markers[row_idx % len(markers)]
        for tv, vv in zip(t, meal):
            col = int(round((tv - tmin) / tspan * (W - 1)))
            row = int(round((1.0 - (vv - gmin) / gspan) * (H - 1)))
            grid[row][col] = marker
    lines.append(
        f"g vs t  (per-meal rows; t: {tmin:g} .. {tmax:g}, value: {gmin:g} .. {gmax:g})"
    )
    for row in range(H):
        val = gmax - row / (H - 1) * gspan
        lines.append(f"{val:8.3g} |{''.join(grid[row])}|")
    lines.append(f"{'':8}  +{'-' * W}+")
    xlabels = [f"{tmin + frac * tspan:g}" for frac in (0.0, 0.25, 0.5, 0.75, 1.0)]
    lines.append(f"{'':8}  {''.join(c.center(W // 4) for c in xlabels)}")
    print("```text")
    print("\n".join(lines))
    print("```")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="PFun CMA scenario demo (timeseries ASCII plots)"
    )
    parser.add_argument(
        "--scenario", choices=sorted(SCENARIOS), default=BASELINE_SCENARIO.slug
    )
    parser.add_argument(
        "--pts", type=int, default=97, help="number of points in the 24 h trace"
    )
    parser.add_argument("--save", metavar="FILE", default=None)
    parser.add_argument("--skip-docstring", action="store_true")
    args = parser.parse_args(argv)

    t = np.linspace(0, 24, args.pts)
    defn = SCENARIOS[args.scenario]

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        if not args.skip_docstring:
            print_docstring()
            print()
        df, g, kwargs = compute_as_dataframe(defn, t)
        describe_scenario(defn, t, kwargs)
        print_dataframe(df)
        print()
        plot_timeseries_ascii(df, g)
    content = buf.getvalue()
    sys.stdout.write(content)
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        with open(args.save, "w", encoding="utf-8") as fh:
            fh.write(content)


if __name__ == "__main__":
    main()
