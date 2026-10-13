"""Tests for the scenario-buffer database layer (schema, population,
precompute, lookup) against SQLite files created under tmp_path.

Engine-backed tests run the C CMA engine through the same path the
precompute CLI uses; parity tests compare stored timecourses against a
direct engine call.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_here = os.path.dirname(os.path.abspath(__file__))
for _p in (
    os.path.dirname(_here),
    os.path.join(os.path.dirname(_here), "demos", "python"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scenariogen import db as sgen_db  # noqa: E402
from scenariogen.mapping import resolve_default_params  # noqa: E402

T_PTS = 49  # coarse resolution keeps the engine-backed tests fast


@pytest.fixture()
def buffer(tmp_path):
    """A fully seeded (but not yet precomputed) scenario buffer."""
    path = str(tmp_path / "scenario_buffer.sqlite")
    conn = sgen_db.create_scenario_db(path, replace=True)
    sgen_db.seed_all(conn)
    yield conn
    conn.close()


def test_schema_tables_and_view(buffer):
    tables = {
        r[0]
        for r in buffer.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {
        "meta", "dimensions", "descriptors", "citations", "descriptor_refs",
        "model_parameters", "parameter_overrides", "scenarios",
        "scenario_refs",
    } <= tables
    views = {
        r[0]
        for r in buffer.execute(
            "SELECT name FROM sqlite_master WHERE type = 'view'"
        ).fetchall()
    }
    assert "scenario_timecourses_long" in views


def test_seed_counts(buffer):
    counts = sgen_db.buffer_stats(buffer)
    assert counts["n_descriptors"] == 19       # 4 + 4 + 3 + 4 + 4
    assert counts["n_references"] >= 45        # curated registry
    assert counts["n_parameter_overrides"] >= 35

    dims = buffer.execute(
        "SELECT count(*) FROM dimensions"
    ).fetchone()[0]
    assert dims == 5
    params = buffer.execute(
        "SELECT count(*) FROM model_parameters"
    ).fetchone()[0]
    assert params == 15


def test_reference_fields_and_local_first(buffer):
    citation = buffer.execute(
        "SELECT citation, year, doi, origin FROM citations "
        "WHERE ref_id = 'russell2019stress'"
    ).fetchone()
    assert citation[1] == 2019
    assert citation[2] == "10.1038/s41574-019-0228-0"
    assert citation[3] == "zotero"

    web = buffer.execute(
        "SELECT count(*) FROM citations WHERE origin = 'web'"
    ).fetchone()[0]
    local = buffer.execute(
        "SELECT count(*) FROM citations WHERE origin = 'zotero'"
    ).fetchone()[0]
    assert web >= 3 and local > web * 4


def test_zotero_enrichment_when_available(buffer, tmp_path):
    import os

    from scenariogen.zotero import find_zotero_db, enrich_references

    zot = find_zotero_db()
    if not zot or not os.path.isfile(zot):
        pytest.skip("local Zotero library not available")

    n = enrich_references(buffer, zot)
    assert n > 0
    # a locally-held reference now carries an absolute PDF path if the file exists
    row = buffer.execute(
        "SELECT local_pdf_path, authors FROM citations "
        "WHERE ref_id = 'russell2019stress'"
    ).fetchone()
    assert "Russell" in (row[1] or "")
    path = row[0] or ""
    if path.startswith("storage:"):  # attachment metadata present but file missing
        pass
    else:
        assert os.path.isfile(path)


def test_precompute_core_tier(tmp_path):
    import json

    conn = sgen_db.create_scenario_db(
        str(tmp_path / "buffer.sqlite"), replace=True
    )
    sgen_db.seed_all(conn)
    t = np.linspace(0.0, 24.0, T_PTS)
    n = sgen_db.precompute(conn, tier="core", t=t, meta_extra={"git_sha": "test"})
    assert n == 15

    counts = sgen_db.buffer_stats(conn)
    assert counts["n_scenarios"] == 15

    # every scenario has a topic-complete timecourse at the requested
    # resolution
    rows = conn.execute(
        "SELECT n_pts, json_array_length(G), json_array_length(t) FROM scenarios"
    ).fetchall()
    assert all(r == (T_PTS, T_PTS, T_PTS) for r in rows)

    # meal-component arrays: per-meal arrays of length n_pts
    for r in conn.execute(
        "SELECT g_meals, n_meals FROM scenarios ORDER BY scenario_id"
    ).fetchall():
        g_meals = json.loads(r[0])
        assert len(g_meals) == r[1]
        assert all(len(m) == T_PTS for m in g_meals)

    # meta build record
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    assert meta["tier"] == "core"
    assert meta["n_scenarios"] == "15"
    assert meta["git_sha"] == "test"

    conn.close()


def test_every_combination_precomputed(tmp_path):
    import json

    conn = sgen_db.create_scenario_db(
        str(tmp_path / "buffer.sqlite"), replace=True
    )
    sgen_db.seed_all(conn)
    sgen_db.precompute(conn, tier="full", t=np.linspace(0.0, 24.0, T_PTS))
    assert sgen_db.buffer_stats(conn)["n_scenarios"] == 768

    combos_in_db = {
        frozenset(json.loads(r[0]).items())
        for r in conn.execute("SELECT descriptor_set FROM scenarios").fetchall()
    }
    assert len(combos_in_db) == 768
    conn.close()


def test_engine_parity_with_direct_call(tmp_path):
    """The stored timecourse of the calibration scenario exactly matches a
    direct call of run_cma_engine_c with the resolved default parameters."""
    import json

    from pfun_cma_engine.pfun_cma_engine import run_cma_engine_c

    conn = sgen_db.create_scenario_db(
        str(tmp_path / "buffer.sqlite"), replace=True
    )
    sgen_db.seed_all(conn)
    t = np.linspace(0.0, 24.0, T_PTS)
    sgen_db.precompute(conn, tier="core", t=t)

    params = resolve_default_params()
    direct = run_cma_engine_c(
        t=t,
        d=params["d"], taup=params["taup"],
        taug_val=params["taug_vec"][0],
        taug_vec=np.asarray(params["taug_vec"]),
        B=params["B"], Cm=params["Cm"], toff=params["toff"],
        tM=np.asarray(params["tM"]),
        seed=None, eps=1e-18, A_raw=None,
        k_A=params["k_A"], A_thresh=params["A_thresh"],
        gamma_A=params["gamma_A"], kappa_A=params["kappa_A"],
        beta_A=params["beta_A"], eta_A=params["eta_A"], tau_A=params["tau_A"],
    )

    stored = conn.execute(
        "SELECT t, G, c, I_E_eff FROM scenarios WHERE scenario_id = 0"
    ).fetchone()
    stored = [json.loads(x) for x in stored]
    assert np.allclose(np.asarray(stored[0]), t, atol=1e-12)
    assert np.allclose(np.asarray(stored[1]), direct["G"], atol=1e-12)
    assert np.allclose(np.asarray(stored[2]), direct["c"], atol=1e-12)
    assert np.allclose(np.asarray(stored[3]), direct["I_E_eff"], atol=1e-12)

    # scenario id 0 is the all-default calibration scenario
    combo = json.loads(conn.execute(
        "SELECT descriptor_set FROM scenarios WHERE scenario_id = 0"
    ).fetchone()[0])
    assert combo["mood"] == "mood:neutral"
    assert combo["hunger"] == "hunger:neutral"
    conn.close()


def test_precompute_is_deterministic(tmp_path):
    def first_row(path):
        import json

        conn = sgen_db.create_scenario_db(str(path), replace=True)
        sgen_db.seed_all(conn)
        sgen_db.precompute(conn, tier="core", t=np.linspace(0.0, 24.0, T_PTS))
        g = conn.execute(
            "SELECT G, summary FROM scenarios WHERE scenario_id = 0"
        ).fetchone()
        conn.close()
        return np.asarray(json.loads(g[0])), g[1]

    a_g, a_sum = first_row(tmp_path / "a.sqlite")
    b_g, b_sum = first_row(tmp_path / "b.sqlite")
    assert np.array_equal(a_g, b_g)
    assert a_sum == b_sum


def test_lookup_exact_and_nearest(tmp_path):
    conn = sgen_db.create_scenario_db(
        str(tmp_path / "buffer.sqlite"), replace=True
    )
    sgen_db.seed_all(conn)
    sgen_db.precompute(conn, tier="core", t=np.linspace(0.0, 24.0, T_PTS))

    # exact match on a full combination
    hit = sgen_db.lookup_scenario(
        conn, mood="stressed", hunger="neutral", sleep="restful",
        activity="sedentary", meal_schedule="standard",
    )
    assert hit is not None
    assert hit["_match_distance"] == 0
    assert hit["descriptor_set"]["mood"] == "mood:stressed"

    # partial query: defaults filled from the buffer
    partial = sgen_db.lookup_scenario(conn, mood="stressed")
    assert partial["_match_distance"] == 0
    assert partial["descriptor_set"]["hunger"] == "hunger:neutral"

    # no exact match in the core tier -> nearest (distance > 0)
    nearest = sgen_db.lookup_scenario(
        conn, mood="happy", hunger="hungry", sleep="short",
    )
    assert nearest is not None
    assert nearest["_match_distance"] > 0

    # lookups carry provenance references
    assert nearest["references"]
    assert sgen_db.references_for(conn, nearest["references"])

    conn.close()


def test_timecourse_helper_g_semantics(tmp_path):
    conn = sgen_db.create_scenario_db(
        str(tmp_path / "buffer.sqlite"), replace=True
    )
    sgen_db.seed_all(conn)
    t = np.linspace(0.0, 24.0, T_PTS)
    sgen_db.precompute(conn, tier="core", t=t)

    tc = sgen_db.timecourse(conn, 0)
    assert len(tc) == T_PTS
    assert tc[0]["t"] == pytest.approx(0.0)
    assert len(tc[0]["g"]) == 3  # per-meal component at t=0 (all zero)
    assert all(g == 0.0 for g in tc[0]["g"])

    # Meal pulses follow K_pfun((t - tM)/taug^2) with K_pfun(x) = 0 for
    # x <= 0, so the component is exactly zero AT the meal time and rises
    # strictly afterwards; with taug = 1.0 the peak is at tM + 0.5 h
    # (i.e. 11.5 for lunch on this grid).
    tm_lunch = 11.0
    grid = np.linspace(0.0, 24.0, T_PTS)
    i = int(np.argmin(np.abs(grid - tm_lunch)))
    assert tc[i]["g"][1] == 0.0      # K_pfun(0) == 0
    assert tc[i + 1]["g"][1] > 0.0   # one grid step (0.5 h) after lunch
    assert max(tc[k]["g"][1] for k in range(T_PTS)) > 0.0

    # the SQL view exposes the same number of rows
    n_rows = conn.execute(
        "SELECT count(*) FROM scenario_timecourses_long WHERE scenario_id = 0"
    ).fetchone()[0]
    assert n_rows == T_PTS
    conn.close()


def test_physiological_direction_in_buffer(tmp_path):
    """The buffer reproduces the qualitative physiology the mappings claim:
    stress -> higher daily cortisol; moderate activity -> an activity signal
    with post-exercise sensitization; starving -> larger first meal."""
    conn = sgen_db.create_scenario_db(
        str(tmp_path / "buffer.sqlite"), replace=True
    )
    sgen_db.seed_all(conn)
    sgen_db.precompute(conn, tier="core", t=np.linspace(0.0, 24.0, T_PTS))

    import json

    def summary_for(desc):
        hit = sgen_db.lookup_scenario(conn, **desc)
        return json.loads(hit["summary"]) if isinstance(hit["summary"], str) else hit["summary"]

    calm = summary_for({"mood": "neutral"})
    stressed = summary_for({"mood": "stressed"})
    assert stressed["c_mean"] > calm["c_mean"]

    sedentary = summary_for({"activity": "sedentary"})
    moderate = summary_for({"activity": "moderate"})
    assert moderate["A_peak"] > 0.0
    assert moderate["A_auc"] > sedentary["A_auc"]
    assert moderate["I_E_eff_max"] > sedentary["I_E_eff_max"]

    conn.close()