"""Tests for the scenario-generator descriptor + physiological mapping layer.

These tests do not require the C engine or DuckDB; they validate the
health-metric catalog, the reference registry and the descriptor -> free
parameter resolution logic.
"""

from __future__ import annotations

import os
import sys

import pytest

_here = os.path.dirname(os.path.abspath(__file__))
for _p in (
    os.path.dirname(_here),               # repo root (pfun_cma_engine etc.)
    os.path.join(os.path.dirname(_here), "demos", "py"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scenariogen.descriptors import (  # noqa: E402
    DESCRIPTORS,
    DIMENSIONS,
    DIMENSION_ORDER,
    combinations,
    core_combinations,
    default_descriptor_id,
    descriptor_id,
)
from scenariogen.mapping import (  # noqa: E402
    CALIBRATION_PARAMS,
    OVERRIDES,
    OVERRIDE_INDEX,
    Override,
    override_ref_ids,
    resolve_default_params,
    resolve_params,
    validate_overrides,
)
from scenariogen.references import REFERENCES, REFERENCE_INDEX  # noqa: E402


def test_dimension_catalog_shape():
    assert set(DIMENSIONS) == {
        "mood", "hunger", "sleep", "activity", "meal_schedule"
    }
    assert DIMENSION_ORDER == (
        "mood", "hunger", "sleep", "activity", "meal_schedule"
    )


@pytest.mark.parametrize(
    "dim,expected_labels",
    [
        ("mood", ["stressed", "tired", "neutral", "happy"]),
        ("hunger", ["sated", "neutral", "hungry", "starving"]),
        ("sleep", ["poor", "short", "restful"]),
        ("activity", ["sedentary", "light", "moderate", "vigorous"]),
        ("meal_schedule", ["standard", "skipped_breakfast", "late_dinner", "heavy_dinner"]),
    ],
)
def test_descriptor_levels(dim, expected_labels):
    got = [d.label for d in DIMENSIONS[dim].descriptors]
    assert got == expected_labels


def test_descriptor_catalog_consistency():
    # every descriptor has unique (dimension, label) and monotonic ordinals
    seen_labels = {}
    for desc in DESCRIPTORS.values():
        assert desc.dimension_id in DIMENSIONS
        assert desc.ordinal >= 0
        key = (desc.dimension_id, desc.label)
        assert key not in seen_labels, f"duplicate {key}"
        seen_labels[key] = desc.ordinal

    for dim in DIMENSIONS.values():
        ordinals = sorted(d.ordinal for d in dim.descriptors)
        assert ordinals == list(range(len(dim.descriptors)))
        # the default descriptor must exist
        default = descriptor_id(dim.dimension_id, dim.default_descriptor)
        assert default in DESCRIPTORS


def test_combinations_cross_product_and_core():
    assert len(combinations()) == 4 * 4 * 3 * 4 * 4  # 768
    assert len(core_combinations()) == 1 + 3 + 3 + 2 + 3 + 3  # 15

    combos = combinations()
    keys = set(combos[0])
    assert keys == set(DIMENSION_ORDER)
    # each combination uses valid descriptor ids
    for combo in combos:
        for dim, desc_id in combo.items():
            assert desc_id in DESCRIPTORS
            assert desc_id.split(":", 1)[0] == dim
            assert desc_id == descriptor_id(dim, DESCRIPTORS[desc_id].label)
    # the all-default combination is present
    assert {"mood": "mood:neutral", "hunger": "hunger:neutral",
            "sleep": "sleep:restful", "activity": "activity:sedentary",
            "meal_schedule": "meal_schedule:standard"} in combos


def test_override_registry_integrity():
    validate_overrides()  # raises on unknown descriptor/ref
    for ov in OVERRIDES:
        assert isinstance(ov, Override)
        assert ov.op in {"set", "mul", "add"}
        assert ov.descriptor_id in DESCRIPTORS
        assert ov.ref_id in REFERENCE_INDEX
        assert ov.param_name in CALIBRATION_PARAMS
        assert OVERRIDE_INDEX[ov.descriptor_id]  # every descriptor linked


def test_reference_registry_local_first():
    # the majority of references come from the local Zotero library
    origins = {}
    for ref in REFERENCES:
        origins.setdefault(ref.origin, 0)
        origins[ref.origin] += 1
        assert ref.ref_id == ref.ref_id  # stable keys
        assert ref.citation
        assert ref.doi or ref.url
    assert origins.get("zotero", 0) > origins.get("web", 0) * 4
    # every reference cited by a descriptor override exists in the registry
    cited = {r.ref_id for _desc in OVERRIDE_INDEX.values() for r in _desc}
    assert cited <= set(REFERENCE_INDEX)


def test_references_cover_dimension_channels():
    # sanity: each physiological channel has at least one citation
    assert {"russell2019stress", "feder2004cortisol"} <= set(REFERENCE_INDEX)
    assert {"brunstrom2011satiety", "berthoud2011appetite"} <= set(REFERENCE_INDEX)
    assert {"vanleeuwen2010sleep", "qian2018circadian"} <= set(REFERENCE_INDEX)
    assert {"frampton2021exercise", "richter2013glut4"} <= set(REFERENCE_INDEX)
    assert {"bandin2014meal", "zecevic2023timing"} <= set(REFERENCE_INDEX)


def test_resolve_default_params_matches_calibration():
    params = resolve_default_params()
    for key in ("d", "taup", "B", "Cm", "toff", "k_A", "A_thresh",
                "gamma_A", "kappa_A", "beta_A", "eta_A", "tau_A"):
        assert params[key] == CALIBRATION_PARAMS[key]
    assert params["tM"] == (7.0, 11.0, 17.5)
    assert params["taug_vec"] == (1.0, 1.0, 1.0)
    assert params["pulses"] == ()


def test_resolve_params_is_deterministic_and_isolated():
    a = resolve_params({"mood": "mood:stressed"})
    b = resolve_params({"mood": "mood:stressed"})
    assert a == b
    assert a is not b  # fresh copies
    assert resolve_params({})["taup"] == CALIBRATION_PARAMS["taup"]


def test_mood_stress_raises_cortisol_tone():
    params = resolve_params({"mood": "mood:stressed"})
    assert params["taup"] == pytest.approx(0.76)           # cortisol amplitude up
    assert params["B"] == pytest.approx(0.05 * 1.03)       # basal glucose up
    # tired is a milder version of the same channel: it still lowers taup
    # (raising cortisol tone) but less than stress does, so the ordering in
    # taup is baseline > tired > stressed
    tired = resolve_params({"mood": "mood:tired"})
    assert params["taup"] < tired["taup"] < CALIBRATION_PARAMS["taup"]


def test_mood_happy_lowers_cortisol_tone():
    params = resolve_params({"mood": "happy"})
    assert params["taup"] == pytest.approx(1.417582418)


@pytest.mark.parametrize(
    "descriptor, expected_amplitude_ratio",
    [
        ({"mood": "stressed"}, 1.25),
        ({"mood": "tired"}, 1.11),
        ({"mood": "happy"}, 0.91),
        ({"sleep": "poor"}, 1.09),
        ({"sleep": "short"}, 1.18),
    ],
)
def test_cortisol_overrides_match_documented_amplitude_changes(
    descriptor, expected_amplitude_ratio
):
    base_tau = CALIBRATION_PARAMS["taup"]
    scenario_tau = resolve_params(descriptor)["taup"]
    base_amplitude = 1.0 / (1.0 + base_tau)
    scenario_amplitude = 1.0 / (1.0 + scenario_tau)
    assert scenario_amplitude / base_amplitude == pytest.approx(
        expected_amplitude_ratio
    )


def test_hunger_starving_larger_earlier_meals():
    params = resolve_params({"hunger": "hunger:starving"})
    assert params["B"] == CALIBRATION_PARAMS["B"]
    assert params["taug_vec"] == pytest.approx((1.0 * 1.20,) * 3)
    assert params["tM"] == pytest.approx((6.5, 11.0, 17.5))
    # in combination with stress the overrides stack deterministically
    combo = resolve_params({"mood": "stressed", "hunger": "starving"})
    assert combo["B"] == pytest.approx(0.05 * 1.03)
    assert combo["taup"] == pytest.approx(0.76)


@pytest.mark.parametrize(
    "schedule, schedule_times, schedule_widths",
    [
        ("skipped_breakfast", (11.0, 17.5), (1.4, 1.1)),
        ("late_dinner", (7.0, 11.0, 20.5), (1.0, 1.0, 1.2)),
        ("heavy_dinner", (7.0, 11.0, 19.0), (1.0, 1.0, 1.35)),
    ],
)
@pytest.mark.parametrize(
    "hunger, width_multiplier",
    [("sated", 0.90), ("neutral", 1.0), ("hungry", 1.08), ("starving", 1.20)],
)
def test_hunger_composes_with_nonstandard_meal_schedules(
    schedule, schedule_times, schedule_widths, hunger, width_multiplier
):
    params = resolve_params({"hunger": hunger, "meal_schedule": schedule})
    expected_times = schedule_times
    if hunger == "starving" and schedule != "skipped_breakfast":
        expected_times = (6.5, *schedule_times[1:])

    assert params["tM"] == pytest.approx(expected_times)
    assert len(params["tM"]) == len(schedule_times)
    assert params["taug_vec"] == pytest.approx(
        tuple(width * width_multiplier for width in schedule_widths)
    )
    assert params["B"] == CALIBRATION_PARAMS["B"]


def test_appetite_and_meal_size_overrides_leave_basal_bias_unchanged():
    for descriptor in (
        {"hunger": "sated"},
        {"hunger": "hungry"},
        {"hunger": "starving"},
        {"meal_schedule": "heavy_dinner"},
    ):
        assert resolve_params(descriptor)["B"] == CALIBRATION_PARAMS["B"]


def test_activity_levels_set_pulses_and_gains():
    assert resolve_params({"activity": "sedentary"})["pulses"] == ()
    light = resolve_params({"activity": "light"})
    assert light["pulses"] == ((12.5, 0.9, 0.18),)
    assert light["gamma_A"] == pytest.approx(0.12)
    moderate = resolve_params({"activity": "moderate"})
    assert moderate["pulses"] == ((6.75, 0.55, 0.55),)
    assert moderate["tau_A"] == pytest.approx(3.0)
    vigorous = resolve_params({"activity": "vigorous"})
    assert vigorous["pulses"] == ((6.75, 0.50, 0.85),)
    assert vigorous["eta_A"] == pytest.approx(0.60)
    assert vigorous["tau_A"] == pytest.approx(4.0)


def test_meal_schedule_variants():
    skipped = resolve_params({"meal_schedule": "skipped_breakfast"})
    assert skipped["tM"] == (11.0, 17.5)          # two meals
    assert skipped["taug_vec"] == (1.4, 1.1)
    late = resolve_params({"meal_schedule": "late_dinner"})
    assert late["tM"] == (7.0, 11.0, 20.5)
    heavy = resolve_params({"meal_schedule": "heavy_dinner"})
    assert heavy["tM"] == (7.0, 11.0, 19.0)
    assert heavy["taug_vec"] == (1.0, 1.0, 1.35)
    assert heavy["B"] == CALIBRATION_PARAMS["B"]


def test_label_forms_are_accepted():
    a = resolve_params({"mood": "stressed", "activity": "moderate"})
    b = resolve_params({"mood": "mood:stressed", "activity": "activity:moderate"})
    assert a == b


def test_unknown_descriptor_rejected():
    with pytest.raises(ValueError):
        resolve_params({"mood": "euphoric"})
    with pytest.raises(ValueError):
        resolve_params({"shoesize": "42"})


def test_override_ref_links_complete():
    for desc_id in OVERRIDE_INDEX:
        refs = override_ref_ids(desc_id)
        assert refs, f"descriptor {desc_id} has no reference backing"
        assert all(r in REFERENCE_INDEX for r in refs)


def test_default_descriptor_helper():
    assert default_descriptor_id("mood") == "mood:neutral"
    assert default_descriptor_id("activity") == "activity:sedentary"