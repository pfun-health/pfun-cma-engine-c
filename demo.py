# coding: utf-8
import argparse
import contextlib
import io
import sys

import numpy as np
import pandas as pd
from pfun_cma_engine import pfun_cma_engine

#: monkey-patched explicitly for clarity
pce = pfun_cma_engine


def print_docstring() -> None:
    """print the docstring for the run_cma_engine_c method.
    """
    print(pce.run_cma_engine_c.__doc__)


def compute_as_dataframe() -> tuple[pd.DataFrame, np.ndarray]:
    """Run the engine and return (DataFrame of 1D variables, 2D meal array g)."""
    t = np.linspace(0, 24, 97)
    soln = pce.run_cma_engine_c(t, 1.0, 1.2, 1.0)
    g = soln.pop("g")
    soln["t"] = t
    df = pd.DataFrame(soln, index=t)
    print(df.to_markdown())
    return df, g


def plot_timeseries_ascii(df: pd.DataFrame, g: np.ndarray, width: int = 60, height: int = 12) -> None:
    """Print a series of ASCII timeseries charts (Variable vs t) for the engine output.

    Renders one chart per 1D column of ``df`` plus a final chart for the per-meal
    array ``g`` (shape ``(n_meals, N)``), overlaying one line per meal row.
    Each chart is wrapped in a fenced code block so it renders correctly as
    markdown (and reads cleanly in a terminal).
    """
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
        lines = []
        lines.append(f"{title}  (t: {tmin:g} .. {tmax:g}, value: {vmin:g} .. {vmax:g})")
        for row in range(H):
            val = vmax - row / (H - 1) * span
            lines.append(f"{val:8.3g} |{''.join(grid[row])}|")
        lines.append(f"{'':8}  +{'-' * W}+")
        xlabels = []
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            xlabels.append(f"{tmin + frac * tspan:g}")
        lines.append(f"{'':8}  {''.join(c.center(W // 4) for c in xlabels)}")
        return "\n".join(lines)

    for col in df.columns:
        if col == "t":
            continue
        print()
        print("```text")
        print(render(df[col].to_numpy(dtype=float), f"{col} vs t", width, height))
        print("```")

    print()
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
    lines.append(f"g vs t  (per-meal rows; t: {tmin:g} .. {tmax:g}, value: {gmin:g} .. {gmax:g})")
    for row in range(H):
        val = gmax - row / (H - 1) * gspan
        lines.append(f"{val:8.3g} |{''.join(grid[row])}|")
    lines.append(f"{'':8}  +{'-' * W}+")
    xlabels = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        xlabels.append(f"{tmin + frac * tspan:g}")
    lines.append(f"{'':8}  {''.join(c.center(W // 4) for c in xlabels)}")
    print("```text")
    print("\n".join(lines))
    print("```")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="PFun CMA demo (timeseries ASCII plots)")
    parser.add_argument("--save", metavar="FILE", default=None,
                        help="also write the captured stdout to FILE (e.g. DEMO_PY_OUTPUT.md)")
    args = parser.parse_args(argv)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_docstring()
        df, g = compute_as_dataframe()
        plot_timeseries_ascii(df, g)
    content = buf.getvalue()
    sys.stdout.write(content)
    if args.save:
        with open(args.save, "w", encoding="utf-8") as fh:
            fh.write("# demo.py session output\n\n")
            fh.write(content)
        print(f"wrote {args.save}", file=sys.stderr)


if __name__ == "__main__":
    main()
