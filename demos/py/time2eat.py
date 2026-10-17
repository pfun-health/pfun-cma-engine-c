#!/usr/bin/env python3
"""/time2eat: recommend mealtimes from the closest matching scenario embedding.

Pipeline:
  1. Collect predefined descriptor choices and build a canonical query matching
     the precomputed scenario documents; find the nearest scenario (the *anchor*).
  2. Gather alternatives: scenarios sharing the anchor's non-meal descriptors
     (sleep, activity, mood, hunger) that differ only in meal_schedule, plus
     the similarity-weighted top-k embedding neighbors.
  3. Score each by time-in-range (TIR) of the precomputed glucose curve,
     weighted by embedding similarity; the best scenario's meal onset times
     (tM) are the recommendation.

The target range defaults to the 5th..95th glucose percentile of the
reference (all-default descriptors) scenario; override with --tir-low/--tir-high.

Usage:
    python demos/py/time2eat.py            # interactive
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scenario_embeddings_demo import (  # noqa: E402
    DEFAULT_DB,
    DEFAULT_MODEL,
    embed_corpus,
    load_scenarios,
    search,
)

from scenariogen.db import ensure_timed_scenario
from scenariogen.descriptors import DIMENSIONS, DIMENSION_ORDER
from scenariogen.mapping import resolve_params

MEAL_DIM = "meal_schedule"
SIM_TEMPERATURE = 0.05


def fmt_clock(h: float) -> str:
    """Format a floating-point hour as HH:MM."""
    total = int(round((h % 24.0) * 60))
    return f"{total // 60 % 24:02d}:{total % 60:02d}"


def load_curves(db_path: str, scenarios: list[dict]) -> None:
    """Attach glucose curve, meal times (tM) and +/-shift variants.

    Each base scenario gets ``variants``: the pre-computed alternative
    scenarios with shifted mealtimes (same descriptor set, ``meal_shift``
    not NULL), built by ``build_scenario_db.py --meal-shifts``.
    """
    conn = sqlite3.connect(db_path)
    rows = {
        r[0]: r for r in conn.execute("SELECT scenario_id, G, params FROM scenarios")
    }
    by_desc: dict[str, list[dict]] = {}
    for sid, title, dset, shift, g, params in conn.execute(
        "SELECT scenario_id, title, descriptor_set, meal_shift, G, params "
        "FROM scenarios WHERE meal_shift IS NOT NULL ORDER BY scenario_id"
    ):
        by_desc.setdefault(dset, []).append(
            {
                "id": sid,
                "title": title,
                "shift": json.loads(shift),
                "G": np.asarray(json.loads(g), dtype=float),
                "tM": [float(x) for x in json.loads(params)["tM"]],
            }
        )
    base_desc = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT scenario_id, descriptor_set FROM scenarios "
            "WHERE meal_shift IS NULL"
        )
    }
    conn.close()
    for s in scenarios:
        _, g, params = rows[s["id"]]
        s["G"] = np.asarray(json.loads(g), dtype=float)
        s["tM"] = [float(x) for x in json.loads(params)["tM"]]
        s["variants"] = by_desc.get(base_desc[s["id"]], [])


def reference_range(scenarios: list[dict]) -> tuple[float, float]:
    """5th..95th glucose percentile of the all-default scenario."""
    from scenariogen.descriptors import DIMENSION_ORDER, default_descriptor_id

    default = {d: default_descriptor_id(d) for d in DIMENSION_ORDER}
    for s in scenarios:
        if s["descriptors"] == default:
            lo, hi = np.percentile(s["G"], [5, 95])
            return float(lo), float(hi)
    allg = np.concatenate([s["G"] for s in scenarios])
    lo, hi = np.percentile(allg, [25, 75])
    return float(lo), float(hi)


def time_in_range(G: np.ndarray, lo: float, hi: float) -> float:
    return float(np.mean((G >= lo) & (G <= hi)))


def recommend(scenarios, hits, lo: float, hi: float) -> dict:
    """Pick the healthiest meal-timing alternative near the anchor scenario."""
    anchor_i, anchor_sim = hits[0]
    anchor = scenarios[anchor_i]
    state = {k: v for k, v in anchor["descriptors"].items() if k != MEAL_DIM}

    cand: dict[int, float] = {i: sim for i, sim in hits}
    for i, s in enumerate(scenarios):
        if i not in cand and all(
            s["descriptors"].get(k) == v for k, v in state.items()
        ):
            cand[i] = anchor_sim  # same physiological state, other meal plan

    best = None
    for i, sim in cand.items():
        weight = float(np.exp((sim - anchor_sim) / SIM_TEMPERATURE))
        for s in [scenarios[i], *scenarios[i].get("variants", [])]:
            tir = time_in_range(s["G"], lo, hi)
            score = tir * weight
            if best is None or score > best["score"]:
                best = {"scenario": s, "tir": tir, "score": score, "sim": sim}
    best: Dict[str, Any]  # type: ignore
    best["anchor"] = anchor
    best["anchor_tir"] = time_in_range(anchor["G"], lo, hi)
    return best


def show(rec: dict, lo: float, hi: float) -> None:
    """Display the recommended meal timing and associated information."""
    a, b = rec["anchor"], rec["scenario"]
    print(f"Closest scenario: {a['title']}")
    print(
        f"  meals: {', '.join(fmt_clock(t) for t in a['tM'])}"
        f"  | TIR {rec['anchor_tir']:.0%} (range {lo:.2f}-{hi:.2f})"
    )
    print(f"Healthiest alternative: {b['title']}")
    print(f"  TIR {rec['tir']:.0%}  (similarity {rec['sim']:.3f})")
    labels = ["breakfast", "lunch", "dinner"]
    times = b["tM"]
    names = labels if len(times) == 3 else [f"meal {i + 1}" for i in range(len(times))]
    plan = ", ".join(f"{n} {fmt_clock(t)}" for n, t in zip(names, times))
    print(f'Recommended time2eat: "{plan}"')


def main() -> None:
    """Main entry point for the time2eat CLI."""

    # Parse command-line arguments and initialize the embedding model.
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])  # type: ignore
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--tir-low", type=float)
    ap.add_argument("--tir-high", type=float)
    args = ap.parse_args()

    try:
        from fastembed import TextEmbedding
    except ImportError:
        sys.exit("fastembed missing: run `uv sync --group demo`")

    # Load scenarios and their glucose curves from the database.
    scenarios = load_scenarios(args.db)
    load_curves(args.db, scenarios)

    # Determine the reference TIR range.
    lo, hi = reference_range(scenarios)
    lo = args.tir_low if args.tir_low is not None else lo
    hi = args.tir_high if args.tir_high is not None else hi

    # Initialize the embedding model and embed the scenario documents.
    model = TextEmbedding(model_name=args.model)
    matrix = embed_corpus(model, [s["doc"] for s in scenarios])

    def parse_clock(value: str) -> float | None:
        """Parse a 24-hour HH:MM time into an hour-of-day value."""
        try:
            hour, minute = (int(part) for part in value.split(":"))
        except ValueError:
            return None
        if not 0 <= hour < 24 or not 0 <= minute < 60:
            return None
        return hour + minute / 60.0

    def prompt_query() -> tuple[dict, tuple[float, ...]] | None:
        """Prompt for levels and render them like the precomputed documents."""
        selected = {}
        for dim_id in DIMENSION_ORDER:
            dim = DIMENSIONS[dim_id]
            options = list(dim.descriptors)
            default = next((d for d in options if d.label == dim.default_descriptor), options[0])
            print(f"\n{dim.name}:")
            for index, desc in enumerate(options, 1):
                suffix = " (default)" if desc == default else ""
                print(f"  {index}. {desc.label.replace('_', ' ')}{suffix}")
            while True:
                answer = input(f"Choose [1-{len(options)}, Enter={default.label}]: ").strip()
                if answer.lower() in {"q", "quit", "exit"}:
                    return None
                if not answer:
                    choice = default
                    break
                if answer.isdigit() and 1 <= int(answer) <= len(options):
                    choice = options[int(answer) - 1]
                    break
                print("Enter an option number, or press Enter for the default.")
            selected[dim_id] = choice

        params = resolve_params({dim: selected[dim].descriptor_id for dim in DIMENSION_ORDER})
        labels = ["breakfast", "lunch", "dinner"]
        meal_labels = labels if len(params["tM"]) == 3 else labels[-len(params["tM"]):]
        times = []
        print("\nEstimated meal times (24-hour HH:MM):")
        for label, default_time in zip(meal_labels, params["tM"]):
            while True:
                answer = input(f"  {label.title()} [Enter={fmt_clock(default_time)}]: ").strip()
                if answer.lower() in {"q", "quit", "exit"}:
                    return None
                if not answer:
                    times.append(float(default_time))
                    break
                parsed = parse_clock(answer)
                if parsed is not None:
                    times.append(parsed)
                    break
                print("Enter a 24-hour time such as 07:30, or press Enter for the default.")
        return selected, tuple(times)

    print("Select a predefined state for each dimension. Enter accepts the default; q exits.")
    while True:
        try:
            prompted = prompt_query()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if prompted is None:
            break
        selected, meal_times = prompted
        descriptor_set = {dim: selected[dim].descriptor_id for dim in DIMENSION_ORDER}
        conn = sqlite3.connect(args.db)
        try:
            scenario_id, inserted = ensure_timed_scenario(conn, descriptor_set, meal_times)
        finally:
            conn.close()
        if inserted:
            print("Added the selected state and estimated meal times to the scenario database.")
            scenarios = load_scenarios(args.db)
            load_curves(args.db, scenarios)
            matrix = embed_corpus(model, [s["doc"] for s in scenarios])
        query = next(s["doc"] for s in scenarios if s["id"] == scenario_id)
        print(f"\nMatching state: {query}")
        hits = search(model, matrix, query, args.top_k)
        show(recommend(scenarios, hits, lo, hi), lo, hi)
        while True:
            try:
                action = input(
                    "\n\033[32m[Enter] to make another query, [q] to exit: \033[0m"
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                action = "q"
            if not action or action in {"q", "quit", "exit"}:
                break
            print("Press Enter to make another query, or q to exit.")
        if action:
            break


if __name__ == "__main__":
    main()
