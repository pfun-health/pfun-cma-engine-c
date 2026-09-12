#!/usr/bin/env python3
"""Query the precomputed CMA scenario buffer.

Usage
-----
    python demos/python/query_scenario_db.py --mood stressed --hunger hungry
                                            [--sleep restful]
                                            [--activity light]
                                            [--meal-schedule standard]
                                            [--db data/scenario_buffer.duckdb]
                                            [--summary-only]
                                            [--timecourse]
                                            [--references]

Looks up the closest precomputed scenario without invoking the engine.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _setup_sys_path() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    for p in (root, here):
        if p not in sys.path:
            sys.path.insert(0, p)


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the CMA scenario buffer")
    parser.add_argument("--db", default=None, help=".duckdb path")
    parser.add_argument("--mood", default=None)
    parser.add_argument("--hunger", default=None)
    parser.add_argument("--sleep", default=None)
    parser.add_argument("--activity", default=None)
    parser.add_argument("--meal-schedule", default=None)
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--timecourse", action="store_true")
    parser.add_argument("--references", action="store_true")
    args = parser.parse_args()

    _setup_sys_path()
    from scenariogen import db as sgen_db

    conn = sgen_db.create_scenario_db(args.db)
    scenario = sgen_db.lookup_scenario(
        conn,
        mood=args.mood, hunger=args.hunger, sleep=args.sleep,
        activity=args.activity, meal_schedule=args.meal_schedule,
    )
    if scenario is None:
        print("no precomputed scenarios in buffer")
        conn.close()
        return 1

    dist = scenario.get("_match_distance", 0)
    match = "exact" if dist == 0 else f"nearest (distance {dist})"
    print(f"scenario_id     : {scenario['scenario_id']}  [{match}]")
    print(f"slug            : {scenario['slug']}")
    print(f"title           : {scenario['title']}")
    print(f"descriptor_set  : {json.dumps(scenario['descriptor_set'], indent=2)}")

    print("summary:")
    print(json.dumps(scenario["summary"], indent=2))

    if args.references:
        print("references:")
        for ref in sgen_db.references_for(conn, scenario["references"]):
            print(f"  - [{ref['ref_id']}] ({ref['year']}) {ref['citation']}")

    if args.timecourse and not args.summary_only:
        tc = sgen_db.timecourse(conn, scenario["scenario_id"])
        print(f"timecourse: {len(tc)} points")
        for pt in tc[:5]:
            print(f"  t={pt['t']:.2f}  G={pt['G']:.3f}  A={pt['A']:.3f}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())