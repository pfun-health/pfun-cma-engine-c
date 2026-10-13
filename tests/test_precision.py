"""Acceptance tests for model input/output precision."""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from precision_report import (
    FP16_FAILURE_THRESHOLD,
    FP32_SCALED_TOLERANCE,
    analyze_precision,
)


@pytest.fixture(scope="module")
def precision_results():
    return analyze_precision()[1]


def test_float32_boundaries_meet_error_budget(precision_results):
    assert precision_results["FP32"]["max_scaled_error"] <= FP32_SCALED_TOLERANCE


def test_float16_boundaries_exceed_error_budget(precision_results):
    assert precision_results["FP16"]["max_scaled_error"] > FP16_FAILURE_THRESHOLD
