"""Scenario buffer: SQLite schema creation and population methods.

This module implements the database layer of the scenario generator.  It
creates and populates a single-file SQLite database (``scenario_buffer``)
that collates, per precomputed scenario combination:

- the *free parameters* resolved from the health-metric descriptors
  (``scenarios.params``),
- the *descriptors* themselves (``descriptors``, ``scenarios.descriptor_set``),
- the *peer-reviewed references* supporting each mapping
  (``references``, ``descriptor_refs``, ``parameter_overrides``),
- the *specific timecourse* produced by the CMA engine
  (wide-format JSON-array TEXT columns on ``scenarios`` + the long-format view
  ``scenario_timecourses_long``).

The resulting file is the "precomputed scenario buffer": client-facing
scenario generator integrations can answer health-state queries from the
buffer (``lookup_scenario``) without calling the engine - and therefore
without invoking any model/solver at request time.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dimensions (
        dimension_id       TEXT PRIMARY KEY,
        name               TEXT NOT NULL,
        description        TEXT,
        default_descriptor TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS descriptors (
        descriptor_id     TEXT PRIMARY KEY,
        dimension_id      TEXT NOT NULL REFERENCES dimensions(dimension_id),
        label             TEXT NOT NULL,
        ordinal           INTEGER NOT NULL,
        description       TEXT,
        physiological_note TEXT,
        UNIQUE (dimension_id, label)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS citations (
        ref_id           TEXT PRIMARY KEY,
        citation         TEXT NOT NULL,
        authors          TEXT,
        year             INTEGER,
        title            TEXT,
        journal          TEXT,
        doi              TEXT,
        url              TEXT,
        zotero_item_id   INTEGER,
        local_pdf_path   TEXT,
        origin           TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS descriptor_refs (
        descriptor_id TEXT NOT NULL REFERENCES descriptors(descriptor_id),
        ref_id        TEXT NOT NULL REFERENCES citations(ref_id),
        note          TEXT,
        PRIMARY KEY (descriptor_id, ref_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_parameters (
        param_name    TEXT PRIMARY KEY,
        description   TEXT,
        default_value TEXT,
        is_free       BOOLEAN NOT NULL,
        domain        TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS parameter_overrides (
        descriptor_id TEXT NOT NULL REFERENCES descriptors(descriptor_id),
        param_name    TEXT NOT NULL,
        op            TEXT NOT NULL,
        value         TEXT NOT NULL,   -- JSON-encoded scalar or list
        rationale     TEXT,
        ref_id        TEXT NOT NULL REFERENCES citations(ref_id),
        PRIMARY KEY (descriptor_id, param_name, ref_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scenarios (
        scenario_id    INTEGER PRIMARY KEY,
        slug           TEXT UNIQUE NOT NULL,
        title          TEXT,
        descriptor_set TEXT NOT NULL,
        params         TEXT NOT NULL,
        n_meals        INTEGER NOT NULL,
        n_pts          INTEGER NOT NULL,
        t              TEXT,
        G              TEXT,
        g_meals        TEXT,
        I_E            TEXT,
        I_E_eff        TEXT,
        L              TEXT,
        m              TEXT,
        c              TEXT,
        c_mod          TEXT,
        A              TEXT,
        s_A            TEXT,
        a_insulin      TEXT,
        I_S            TEXT,
        summary        TEXT NOT NULL,
        status         TEXT NOT NULL DEFAULT 'precomputed',
        created_at     TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scenario_refs (
        scenario_id INTEGER NOT NULL REFERENCES scenarios(scenario_id),
        ref_id      TEXT NOT NULL REFERENCES citations(ref_id),
        role        TEXT,
        PRIMARY KEY (scenario_id, ref_id)
    )
    """,
    """
    CREATE VIEW IF NOT EXISTS scenario_timecourses_long AS
    SELECT
        s.scenario_id AS scenario_id,
        json_extract(s.t, '$[' || je.key || ']') AS t,
        json_extract(s.G, '$[' || je.key || ']') AS G,
        (SELECT json_group_array(json_extract(gm.value, '$[' || je.key || ']'))
           FROM json_each(s.g_meals) AS gm) AS g,
        json_extract(s.I_E, '$[' || je.key || ']') AS I_E,
        json_extract(s.I_E_eff, '$[' || je.key || ']') AS I_E_eff,
        json_extract(s.L, '$[' || je.key || ']') AS L,
        json_extract(s.m, '$[' || je.key || ']') AS m,
        json_extract(s.c, '$[' || je.key || ']') AS c,
        json_extract(s.c_mod, '$[' || je.key || ']') AS c_mod,
        json_extract(s.A, '$[' || je.key || ']') AS A,
        json_extract(s.s_A, '$[' || je.key || ']') AS s_A,
        json_extract(s.a_insulin, '$[' || je.key || ']') AS a,
        json_extract(s.I_S, '$[' || je.key || ']') AS I_S
    FROM scenarios AS s, json_each(s.t) AS je
    """,
)

# ---------------------------------------------------------------------------
# connection / schema lifecycle
# ---------------------------------------------------------------------------


def _resolve_db_path(path: str | None) -> str:
    if path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.normpath(
            os.path.join(here, "..", "..", "..", "data", "scenario_buffer.sqlite")
        )
    return os.path.abspath(path)


def create_scenario_db(
    path: str | None = None, *, replace: bool = False
) -> sqlite3.Connection:
    """Open (and if needed create) the scenario buffer database.

    Returns a sqlite3 connection (autocommit).  When ``replace`` is True an existing file
    is dropped first (a full rebuild).
    """
    db_path = _resolve_db_path(path)
    if replace and os.path.exists(db_path):
        os.remove(db_path)
    if not os.path.isdir(os.path.dirname(db_path)):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA synchronous = OFF")
    create_schema(conn)
    return conn


def create_schema(conn) -> None:
    """Create all tables and the long-format view if they do not exist."""
    for ddl in SCHEMA:
        conn.execute(ddl)


def drop_schema(conn) -> None:
    """Drop every scenario-buffer table and view (used by tests/rebuilds)."""
    for name in (
        "scenario_timecourses_long",
        "scenario_refs",
        "scenarios",
        "parameter_overrides",
        "model_parameters",
        "descriptor_refs",
        "citations",
        "descriptors",
        "dimensions",
        "meta",
    ):
        conn.execute(f"DROP TABLE IF EXISTS {name}")
    conn.execute("DROP VIEW IF EXISTS scenario_timecourses_long")


def has_schema(conn) -> bool:
    """True when the core tables exist."""
    rows = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN "
        "('dimensions','descriptors','citations','scenarios')"
    ).fetchone()
    return bool(rows and rows[0] >= 4)


# ---------------------------------------------------------------------------
# seeding
# ---------------------------------------------------------------------------


def seed_dimensions(conn) -> None:
    """Populate dimensions + descriptors (idempotent; re-seeds cleanly)."""
    from scenariogen.descriptors import DESCRIPTORS, DIMENSIONS

    conn.execute("DELETE FROM descriptors")
    conn.execute("DELETE FROM dimensions")
    for dim in DIMENSIONS.values():
        conn.execute(
            "INSERT INTO dimensions (dimension_id, name, description, "
            "default_descriptor) VALUES (?, ?, ?, ?)",
            [dim.dimension_id, dim.name, dim.description, dim.default_descriptor],
        )
    for desc in DESCRIPTORS.values():
        conn.execute(
            "INSERT INTO descriptors (descriptor_id, dimension_id, label, "
            "ordinal, description, physiological_note) VALUES (?, ?, ?, ?, ?, ?)",
            [
                desc.descriptor_id,
                desc.dimension_id,
                desc.label,
                desc.ordinal,
                desc.description,
                desc.physiological_note,
            ],
        )


def seed_parameter_catalog(conn) -> None:
    """Populate model_parameters from mapping.PARAMETER_CATALOG."""
    from scenariogen.mapping import PARAMETER_CATALOG

    conn.execute("DELETE FROM model_parameters")
    for row in PARAMETER_CATALOG:
        conn.execute(
            "INSERT INTO model_parameters (param_name, description, "
            "default_value, is_free, domain) VALUES (?, ?, ?, ?, ?)",
            [row["param_name"], row["description"], row["default_value"],
             row["is_free"] == "true", row["domain"]],
        )


def seed_references(
    conn, *, zotero_db_path: str | None = None, enrich_from_zotero: bool = True
) -> None:
    """Populate references from the curated registry and (optionally) enrich
    against the local Zotero library."""
    from scenariogen.references import REFERENCES

    conn.execute("DELETE FROM citations")
    for ref in REFERENCES:
        conn.execute(
            "INSERT INTO citations (ref_id, citation, authors, year, title, "
            "journal, doi, url, zotero_item_id, local_pdf_path, origin) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ref.ref_id, ref.citation, ref.authors, ref.year, ref.title,
                ref.journal, ref.doi, ref.url, ref.zotero_item_id,
                ref.zotero_pdf_path, ref.origin,
            ],
        )

    if enrich_from_zotero:
        try:
            from scenariogen.zotero import enrich_references
            path = zotero_db_path or _find_default_zotero_db()
            if path and os.path.exists(path):
                enrich_references(conn, path)
        except ImportError:  # pragma: no cover - zotero helper unavailable
            pass


def _find_default_zotero_db() -> str | None:
    candidates = [
        os.environ.get("ZOTERO_DB"),
        os.path.expanduser("~/Zotero/zotero.sqlite"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def link_descriptor_refs(conn) -> None:
    """Fill descriptor_refs + parameter_overrides from mapping.OVERRIDES."""
    from scenariogen.mapping import OVERRIDES, override_ref_ids

    conn.execute("DELETE FROM parameter_overrides")
    conn.execute("DELETE FROM descriptor_refs")

    for ov in OVERRIDES:
        value_json = (
            list(ov.value) if isinstance(ov.value, tuple) else ov.value
        )
        conn.execute(
            "INSERT INTO parameter_overrides (descriptor_id, param_name, op, "
            "value, rationale, ref_id) VALUES (?, ?, ?, ?, ?, ?)",
            [ov.descriptor_id, ov.param_name, ov.op,
             json.dumps(value_json), ov.rationale, ov.ref_id],
        )

    for desc_id in sorted(
        {ov.descriptor_id for ov in OVERRIDES}
    ):
        for ref_id in override_ref_ids(desc_id):
            conn.execute(
                "INSERT INTO descriptor_refs (descriptor_id, ref_id, note) "
                "VALUES (?, ?, ?)",
                [desc_id, ref_id,
                 "reference backing the descriptor's parameter mapping"],
            )


def seed_all(conn, *, zotero_db_path: str | None = None) -> None:
    """Convenience: create schema, seed dimensions, parameters, references
    and the descriptor/reference links."""
    create_schema(conn)
    seed_dimensions(conn)
    seed_parameter_catalog(conn)
    seed_references(conn, zotero_db_path=zotero_db_path)
    link_descriptor_refs(conn)


# ---------------------------------------------------------------------------
# combination generation
# ---------------------------------------------------------------------------

TIERS = ("core", "full")


def generate_combinations(tier: str = "full") -> list[dict[str, str]]:
    """Ordered list of descriptor combinations for a buffer tier.

    ``tier='core'`` yields the all-default scenario plus every single
    dimension perturbed one step (currently 16 scenarios); ``tier='full'``
    yields the full cross-product (currently 768 scenarios).
    """
    from scenariogen.descriptors import combinations, core_combinations

    if tier == "core":
        return core_combinations()
    if tier == "full":
        return combinations()
    raise ValueError(f"unknown tier {tier!r}; expected one of {TIERS}")


# ---------------------------------------------------------------------------
# engine execution + summarization
# ---------------------------------------------------------------------------


def engine_run(params: dict, t) -> dict:
    """Run the CMA engine for a resolved parameter dict, returning the raw
    output dict plus a ``summary`` key.

    Requires the repo root (``pfun_cma_engine``) and ``demos/py``
    (``scenarios``) on ``sys.path`` - the CLI and tests arrange this.
    """
    import numpy as np

    from pfun_cma_engine.pfun_cma_engine import run_cma_engine_c
    from scenarios import build_activity_signal

    t = np.asarray(t, dtype=float)
    pulses = tuple(params.get("pulses") or ())
    A_raw = build_activity_signal(t, pulses) if pulses else None

    kwargs = dict(
        t=t,
        d=float(params["d"]),
        taup=float(params["taup"]),
        taug_val=float(params["taug_vec"][0]),
        taug_vec=np.asarray(params["taug_vec"], dtype=float),
        B=float(params["B"]),
        Cm=float(params["Cm"]),
        toff=float(params["toff"]),
        tM=np.asarray(params["tM"], dtype=float),
        seed=None,
        eps=1e-18,
        A_raw=A_raw,
        k_A=float(params["k_A"]),
        A_thresh=float(params["A_thresh"]),
        gamma_A=float(params["gamma_A"]),
        kappa_A=float(params["kappa_A"]),
        beta_A=float(params["beta_A"]),
        eta_A=float(params["eta_A"]),
        tau_A=float(params["tau_A"]),
    )
    out = run_cma_engine_c(**kwargs)
    out["summary"] = summarize(out, t, params)
    return out


def summarize(out: dict, t, params: dict) -> dict:
    """Collate scalar summary statistics for a scenario timecourse."""
    import numpy as np

    t = np.asarray(t, dtype=float)
    G = np.asarray(out["G"], dtype=float)
    per_meal = [
        np.asarray(g_j, dtype=float) for g_j in out.get("g", [])
    ]
    q05, q95 = np.percentile(G, [5, 95])

    meal_times = np.asarray(params["tM"], dtype=float)
    excursions: list[float] = []
    for tm in meal_times:
        i_start = int(np.argmin(np.abs(t - tm)))
        window = np.where((t >= t[i_start]) & (t <= t[i_start] + 3.0))[0]
        if window.size > 1:
            excursions.append(
                float(np.max(G[window]) - G[window[0]])
            )
        else:
            excursions.append(float("nan"))

    dt = float(t[1] - t[0]) if t.size > 1 else 0.0
    g_auc = sum(float(np.trapezoid(g_j, t)) for g_j in per_meal)

    return {
        "G_mean": float(np.mean(G)),
        "G_std": float(np.std(G)),
        "G_min": float(np.min(G)),
        "G_max": float(np.max(G)),
        "G_p05": float(q05),
        "G_p95": float(q95),
        "t_G_max": float(t[int(np.argmax(G))]),
        "G_range": float(np.max(G) - np.min(G)),
        "meal_excursions": excursions,
        "max_meal_excursion": float(
            np.nanmax(excursions) if excursions else float("nan")
        ),
        "g_auc_total": g_auc,
        "I_E_eff_max": float(np.max(out["I_E_eff"])),
        "I_E_max": float(np.max(out["I_E"])),
        "c_mean": float(np.mean(out["c"])),
        "c_max": float(np.max(out["c"])),
        "c_mod_max": float(np.max(out["c_mod"])),
        "A_peak": float(np.max(out["A"])),
        "A_auc": float(np.trapezoid(np.asarray(out["A"], dtype=float), t)),
    }


def slug_for(descriptor_set: dict[str, str]) -> str:
    """Deterministic slug from a descriptor combination (labels)."""
    from scenariogen.descriptors import DIMENSION_ORDER

    def label(desc_id: str) -> str:
        if ":" in desc_id:
            dim, lab = desc_id.split(":", 1)
            return lab
        return desc_id

    parts = [
        f"{dim}={label(descriptor_set.get(dim, '')) or 'default'}"
        for dim in DIMENSION_ORDER
    ]
    return "__".join(parts)


def title_for(descriptor_set: dict[str, str]) -> str:
    """Human title, e.g. 'stressed / hungry / restful / sedentary / standard'."""
    from scenariogen.descriptors import DIMENSION_ORDER

    def label(desc_id: str) -> str:
        return desc_id.split(":", 1)[1] if ":" in desc_id else desc_id

    return " / ".join(
        label(descriptor_set.get(dim, "")) or "default"
        for dim in DIMENSION_ORDER
    )


# ---------------------------------------------------------------------------
# precompute
# ---------------------------------------------------------------------------


def precompute(
    conn,
    combinations: list[dict[str, str]] | None = None,
    *,
    t=None,
    tier: str = "full",
    progress: bool = False,
    meta_extra: dict[str, str] | None = None,
    on_progress=None,
) -> int:
    """Run the engine for every combination and store results in ``scenarios``.

    Returns the number of scenarios written.  Existing rows are replaced
    (the table is rebuilt per call, keeping determinism).
    """
    import numpy as np

    if combinations is None:
        combinations = generate_combinations(tier)
    if t is None:
        t = np.linspace(0.0, 24.0, 193)

    from scenariogen.mapping import (
        override_ref_ids,
        resolve_params,
    )

    conn.execute("DELETE FROM scenarios")
    conn.execute("DELETE FROM scenario_refs")

    n = len(combinations)
    written = 0
    for i, combo in enumerate(combinations):
        params = resolve_params(combo)
        out = engine_run(params, t)
        summ = out["summary"]

        scenario_id = i
        slug = slug_for(combo)
        desc_json = json.dumps(combo)
        params_json = json.dumps(_jsonable(params))
        summary_json = json.dumps(summ)

        conn.execute(
            "INSERT INTO scenarios (scenario_id, slug, title, descriptor_set, "
            "params, n_meals, n_pts, t, G, g_meals, I_E, I_E_eff, L, m, c, c_mod, "
            "A, s_A, a_insulin, I_S, summary, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'precomputed')",
            [
                scenario_id, slug, title_for(combo), desc_json, params_json,
                int(len(params["tM"])), int(len(t)),
                _arr(t),
                _arr(out["G"]),
                json.dumps([np.asarray(g_j, dtype=float).tolist() for g_j in out["g"]]),
                _arr(out["I_E"]),
                _arr(out["I_E_eff"]),
                _arr(out["L"]),
                _arr(out["m"]),
                _arr(out["c"]),
                _arr(out["c_mod"]),
                _arr(out["A"]),
                _arr(out["s_A"]),
                _arr(out["a"]),
                _arr(out["I_S"]),
                summary_json,
            ],
        )

        # provenance rows: references attached to the mapping of each descriptor
        seen_refs: set[str] = set()
        for dim, desc_id in combo.items():
            role = f"{dim}->{desc_id}"
            for ref_id in override_ref_ids(desc_id):
                seen_refs.add(ref_id)
        for ref_id in sorted(seen_refs):
            conn.execute(
                "INSERT INTO scenario_refs (scenario_id, ref_id, role) "
                "VALUES (?, ?, ?)",
                [scenario_id, ref_id, "descriptor mapping"],
            )

        written += 1
        if progress and (i % 64 == 0 or i == n - 1):
            msg = f"precomputed {i + 1}/{n}"
            if on_progress:
                on_progress(msg)
            else:
                print(f"\r{msg}", end="", flush=True)

    if progress and not on_progress:
        print()

    # record build metadata
    meta = {
        "generator": "scenariogen",
        "tier": tier,
        "n_scenarios": str(written),
        "n_pts": str(len(t)),
        "t_start": str(float(t[0])),
        "t_end": str(float(t[-1])),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sqlite_version": sqlite3.sqlite_version,
    }
    if meta_extra:
        meta.update(meta_extra)
    conn.execute("DELETE FROM meta")
    for k, v in meta.items():
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", [k, v]
        )

    return written


def _arr(a) -> str:
    """JSON-encode a numeric array for a TEXT column."""
    import numpy as np

    return json.dumps(np.asarray(a, dtype=float).tolist())


def _jsonable(params: dict) -> dict:
    """Convert a resolved parameter dict into a JSON-serializable dict."""
    out = {}
    for k, v in params.items():
        if isinstance(v, tuple):
            out[k] = list(v)
        elif isinstance(v, (int, float, str, bool)) or v is None:
            out[k] = v
        else:  # pragma: no cover - defensive
            out[k] = str(v)
    return out


# ---------------------------------------------------------------------------
# query helpers
# ---------------------------------------------------------------------------


def _combo_from_row(row) -> dict[str, str]:
    return json.loads(row[0]) if not isinstance(row[0], dict) else row[0]


def lookup_scenario(conn, **descriptors) -> dict | None:
    """Return the precomputed scenario matching a health-state query.

    Accepts descriptor values as labels (``mood='stressed'``) or full ids
    (``mood='mood:stressed'``).  When every requested dimension matches a
    stored scenario exactly, that scenario is returned; otherwise the
    nearest stored scenario is returned with a ``_match_distance`` field
    (Hamming distance over the requested dimensions).  Returns None when the
    buffer is empty.
    """
    from scenariogen.descriptors import DIMENSION_ORDER, descriptor_id

    def canonical(dim: str, value: str) -> str | None:
        if not value:
            return None
        if ":" in value:
            return value if value.split(":", 1)[0] == dim else None
        candidate = descriptor_id(dim, value)
        exists = conn.execute(
            "SELECT count(*) FROM descriptors WHERE descriptor_id = ?",
            [candidate],
        ).fetchone()[0]
        if exists:
            return candidate
        return None

    query = {
        dim: canonical(dim, val)
        for dim, val in descriptors.items()
        if dim in DIMENSION_ORDER and val
    }
    query = {k: v for k, v in query.items() if v is not None}
    if not query:
        return None

    rows = conn.execute(
        "SELECT descriptor_set, summary, scenario_id FROM scenarios ORDER BY scenario_id"
    ).fetchall()

    best = None
    best_dist = None
    for row in rows:
        combo = json.loads(row[0]) if not isinstance(row[0], dict) else row[0]
        dist = sum(1 for dim, want in query.items() if combo.get(dim) != want)
        if dist == 0:
            best = (row, combo, dist)
            break
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = (row, combo, dist)

    if best is None:
        return None

    row, combo, dist = best
    return _scenario_dict(conn, int(row[2]), combo, match_distance=dist)


def get_scenario(conn, scenario_id: int, *, include_timecourse: bool = True) -> dict:
    """Return one scenario as a plain dict (arrays included)."""
    row = conn.execute(
        "SELECT scenario_id, slug, title, descriptor_set, params, summary, "
        "n_meals, n_pts FROM scenarios WHERE scenario_id = ?",
        [scenario_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"scenario {scenario_id} not found")
    return {
        "scenario_id": int(row[0]),
        "slug": row[1],
        "title": row[2],
        "descriptor_set": json.loads(row[3]) if not isinstance(row[3], dict) else row[3],
        "params": json.loads(row[4]) if not isinstance(row[4], dict) else row[4],
        "summary": json.loads(row[5]) if not isinstance(row[5], dict) else row[5],
        "n_meals": int(row[6]),
        "n_pts": int(row[7]),
    }


def _scenario_dict(
    conn, scenario_id: int, combo: dict[str, str], *, match_distance: int | None = None
) -> dict:
    out = get_scenario(conn, scenario_id)
    if match_distance is not None:
        out["_match_distance"] = match_distance
    rows = conn.execute(
        "SELECT ref_id FROM scenario_refs WHERE scenario_id = ? ORDER BY ref_id",
        [scenario_id],
    ).fetchall()
    out["references"] = [r[0] for r in rows]
    return out


def timecourse(conn, scenario_id: int) -> list[dict]:
    """Long-format timecourse points for a scenario.

    The points are zipped in Python from the wide-format JSON-array columns, which
    keeps the helper independent of SQLite JSON functions; the SQL view
    ``scenario_timecourses_long`` remains available for external consumers.
    """
    row = conn.execute(
        "SELECT t, G, g_meals, I_E, I_E_eff, L, m, c, c_mod, A, s_A, "
        "a_insulin, I_S FROM scenarios WHERE scenario_id = ?",
        [scenario_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"scenario {scenario_id} not found")
    (t, G, g_meals, I_E, I_E_eff, L, m, c, c_mod, A, s_A, a_insulin,
     I_S) = (json.loads(x) for x in row)
    n = len(t)
    n_meals = len(g_meals)
    return [
        {
            "t": t[i],
            "G": G[i],
            "g": [g_meals[j][i] for j in range(n_meals)],
            "I_E": I_E[i],
            "I_E_eff": I_E_eff[i],
            "L": L[i],
            "m": m[i],
            "c": c[i],
            "c_mod": c_mod[i],
            "A": A[i],
            "s_A": s_A[i],
            "a": a_insulin[i],
            "I_S": I_S[i],
        }
        for i in range(n)
    ]


def references_for(conn, ref_ids: list[str] | None = None) -> list[dict]:
    """Reference rows (curated citation strings)."""
    if ref_ids is None:
        rows = conn.execute(
            "SELECT ref_id, citation, year, journal, doi, origin "
            "FROM citations ORDER BY ref_id"
        ).fetchall()
    else:
        marks = ", ".join("?" * len(ref_ids))
        rows = conn.execute(
            "SELECT ref_id, citation, year, journal, doi, origin "
            f"FROM citations WHERE ref_id IN ({marks}) ORDER BY ref_id",
            list(ref_ids),
        ).fetchall()
    return [
        {
            "ref_id": r[0], "citation": r[1], "year": r[2], "journal": r[3],
            "doi": r[4], "origin": r[5],
        }
        for r in rows
    ]


def buffer_stats(conn) -> dict:
    """Aggregate statistics about the buffer for reporting."""
    n_scenarios = conn.execute(
        "SELECT count(*) FROM scenarios"
    ).fetchone()[0]
    n_refs = conn.execute("SELECT count(*) FROM citations").fetchone()[0]
    n_override_rows = conn.execute(
        "SELECT count(*) FROM parameter_overrides"
    ).fetchone()[0]
    n_descriptors = conn.execute(
        "SELECT count(*) FROM descriptors"
    ).fetchone()[0]
    return {
        "n_scenarios": int(n_scenarios),
        "n_references": int(n_refs),
        "n_parameter_overrides": int(n_override_rows),
        "n_descriptors": int(n_descriptors),
    }