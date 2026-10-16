#!/usr/bin/env python3
"""/time2eat: recommend mealtimes from the closest matching scenario embedding.

Pipeline:
  1. Embed the free-text state (e.g. "poor sleep, low activity, happy, late
     dinner, no breakfast") and find the nearest scenario (the *anchor*).
  2. Gather alternatives: scenarios sharing the anchor's non-meal descriptors
     (sleep, activity, mood, hunger) that differ only in meal_schedule, plus
     the similarity-weighted top-k embedding neighbors.
  3. Score each by time-in-range (TIR) of the precomputed glucose curve,
     weighted by embedding similarity; the best scenario's meal onset times
     (tM) are the recommendation.

The target range defaults to the 5th..95th glucose percentile of the
reference (all-default descriptors) scenario; override with --tir-low/--tir-high.

Usage:
    python demos/py/time2eat.py "/time2eat poor sleep, low activity, happy, late dinner"
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

COMMAND = "/time2eat"
MEAL_DIM = "meal_schedule"
SIM_TEMPERATURE = 0.05


def parse_query(text: str) -> str:
    text = text.strip()
    if text.lower().startswith(COMMAND):
        text = text[len(COMMAND):]
    return text.strip(" \t:,")


def fmt_clock(h: float) -> str:
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
        r[0]: r
        for r in conn.execute("SELECT scenario_id, G, params FROM scenarios")
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
    best["anchor"] = anchor
    best["anchor_tir"] = time_in_range(anchor["G"], lo, hi)
    return best


def show(rec: dict, lo: float, hi: float) -> None:
    a, b = rec["anchor"], rec["scenario"]
    print(f"Closest scenario: {a['title']}")
    print(f"  meals: {', '.join(fmt_clock(t) for t in a['tM'])}"
          f"  | TIR {rec['anchor_tir']:.0%} (range {lo:.2f}-{hi:.2f})")
    print(f"Healthiest alternative: {b['title']}")
    print(f"  TIR {rec['tir']:.0%}  (similarity {rec['sim']:.3f})")
    labels = ["breakfast", "lunch", "dinner"]
    times = b["tM"]
    names = labels if len(times) == 3 else [f"meal {i + 1}" for i in range(len(times))]
    plan = ", ".join(f"{n} {fmt_clock(t)}" for n, t in zip(names, times))
    print(f'Recommended time2eat: "{plan}"')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("query", nargs="*", help="e.g. '/time2eat poor sleep, late dinner'")
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

    scenarios = load_scenarios(args.db)
    load_curves(args.db, scenarios)
    lo, hi = reference_range(scenarios)
    lo = args.tir_low if args.tir_low is not None else lo
    hi = args.tir_high if args.tir_high is not None else hi
    model = TextEmbedding(model_name=args.model)
    matrix = embed_corpus(model, [s["doc"] for s in scenarios])

    def run(text: str) -> None:
        q = parse_query(text)
        if not q:
            print(f"Usage: {COMMAND} <describe sleep, activity, mood, meals>")
            return
        hits = search(model, matrix, q, args.top_k)
        show(recommend(scenarios, hits, lo, hi), lo, hi)

    if args.query:
        run(" ".join(args.query))
        return
    print(f"Type e.g. '{COMMAND} poor sleep, low activity, happy, late dinner, "
          "no breakfast'. Empty line exits.")
    while True:
        try:
            line = input("\ntime2eat> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line or line.lower() in {"q", "quit", "exit"}:
            break
        run(line)


if __name__ == "__main__":
    main()
