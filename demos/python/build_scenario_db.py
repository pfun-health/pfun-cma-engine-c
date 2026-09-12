#!/usr/bin/env python3
"""Build the precomputed CMА scenario buffer (DuckDB).

Usage
-----
    python demos/python/build_scenario_db.py [--db data/scenario_buffer.duckdb]
                                             [--tier full|core]
                                             [--pts 193]
                                             [--seed 42]
                                             [--no-precompute]
                                             [--zotero /path/to/zotero.sqlite]

The default target writes ``data/scenario_buffer.duckdb``: one schema +
seeded catalogs (dimensions, descriptors, references, parameter overrides)
and one row per descriptor combination with the full engine timecourse
stored in wide ARRAY columns (plus the long-format SQL view).

Rebuilds are deterministic: same arguments -> identical scenarios table.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def _setup_sys_path() -> None:
    here = os.path.dirname(os.path.abspath(__file__))          # demos/python
    root = os.path.dirname(os.path.dirname(here))              # repo root
    for p in (root, here):
        if p not in sys.path:
            sys.path.insert(0, p)


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the CMA scenario buffer")
    parser.add_argument("--db", default=None, help="output .duckdb path")
    parser.add_argument(
        "--tier", choices=("core", "full"), default="full",
        help="buffer tier (default: full cross-product)",
    )
    parser.add_argument(
        "--pts", type=int, default=193,
        help="timecourse resolution (points over 24 h)",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="engine RNG seed (unused: noise off)"
    )
    parser.add_argument(
        "--no-precompute", action="store_true",
        help="create + seed the schema but do not run the engine",
    )
    parser.add_argument(
        "--zotero", default=None,
        help="path to local Zotero sqlite db (metadata enrichment)",
    )
    args = parser.parse_args()

    import numpy as np

    _setup_sys_path()
    from scenariogen import db as sgen_db

    conn = sgen_db.create_scenario_db(args.db, replace=True)
    print(f"[scenariogen] schema created at {sgen_db._resolve_db_path(args.db)}")

    zotero_path = args.zotero
    if zotero_path is None:
        from scenariogen import zotero as zotero_mod

        zotero_path = zotero_mod.find_zotero_db()
    if zotero_path and os.path.isfile(zotero_path):
        print(f"[scenariogen] enriching references from Zotero: {zotero_path}")
    else:
        print("[scenariogen] Zotero library not found; using curated registry")

    sgen_db.seed_all(conn, zotero_db_path=zotero_path)

    combos = sgen_db.generate_combinations(args.tier)
    print(
        f"[scenariogen] {len(combos)} descriptor combinations "
        f"(tier={args.tier})"
    )

    if not args.no_precompute:
        t = np.linspace(0.0, 24.0, args.pts)
        extra = {"git_sha": _git_sha() or "unknown"}
        n = sgen_db.precompute(
            conn, combos, t=t, tier=args.tier,
            progress=True, meta_extra=extra,
        )
        stats = sgen_db.buffer_stats(conn)
        print(f"[scenariogen] precomputed {n} scenarios")
        print(
            f"[scenariogen] buffer: {stats['n_scenarios']} scenarios | "
            f"{stats['n_descriptors']} descriptors | "
            f"{stats['n_references']} references | "
            f"{stats['n_parameter_overrides']} parameter overrides"
        )

        # quick spot check: the calibration scenario
        cal = sgen_db.lookup_scenario(
            conn, mood="neutral", hunger="neutral", sleep="restful",
            activity="sedentary", meal_schedule="standard",
        )
        if cal:
            s = cal["summary"]
            print(
                f"[scenariogen] calibration check (id={cal['scenario_id']}): "
                f"G_mean={s['G_mean']:.3f} G_max={s['G_max']:.3f} "
                f"max_excursion={s['max_meal_excursion']:.3f}"
            )
    else:
        print("[scenariogen] schema seeded; --no-precompute set, skipping engine")

    conn.close()
    print("[scenariogen] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())