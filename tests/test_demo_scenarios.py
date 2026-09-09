import os
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / 'demos' / 'python'))

from pfun_cma_engine.pfun_cma_engine import run_cma_engine_c
from scenarios import BASELINE_SCENARIO, EVENING_PARTY_SCENARIO, MORNING_RUN_SCENARIO, scenario_kwargs


T = np.linspace(0.0, 24.0, 97)


def _run(defn):
    return run_cma_engine_c(**scenario_kwargs(defn, T))


def test_morning_run_activity_signal_is_bounded():
    kwargs = scenario_kwargs(MORNING_RUN_SCENARIO, T)
    a_raw = kwargs['A_raw']
    assert a_raw is not None
    assert np.all(a_raw >= 0.0)
    assert np.all(a_raw <= 1.0)
    assert float(np.max(a_raw)) > 0.5


def test_morning_run_leaves_post_run_sensitization():
    res = _run(MORNING_RUN_SCENARIO)
    run_end_idx = np.searchsorted(T, 8.0)
    late_morning = slice(run_end_idx, np.searchsorted(T, 11.0))
    assert res['I_E_eff'][late_morning].mean() > res['I_E'][late_morning].mean()


def test_evening_party_lowers_post_dinner_glucose_vs_baseline():
    baseline = _run(BASELINE_SCENARIO)
    party = _run(EVENING_PARTY_SCENARIO)
    dinner_window = slice(np.searchsorted(T, 19.0), np.searchsorted(T, 22.0))
    assert party['G'][dinner_window].mean() < baseline['G'][dinner_window].mean()
