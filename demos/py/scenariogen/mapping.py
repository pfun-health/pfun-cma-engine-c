"""Physiological mapping: qualitative health descriptors -> engine parameters.

This module is the scientific core of the scenario generator.  Each
descriptor level on the health-metric dimensions (mood, hunger, sleep,
activity, meal_schedule) contributes deterministic *overrides* to the free
parameters of the CMA engine.  The resolved parameter set of a scenario is
computed by starting from the calibration (baseline) parameter set and
applying overrides in a fixed dimension order.

Overrides are expressed as (parameter, operation, value, ref_id) with one of
three operations:

- ``set``  : replace the value (used for tuples such as meal times)
- ``mul``  : multiply the value (scalars and per-element for tuples)
- ``add``  : add to the value

The reference in every override row is the peer-reviewed basis for the
physiological assumption; the same table is materialized in the database as
``parameter_overrides`` so the provenance is queryable.

Channel summary (see docs/SCENARIO_DB.md for the full table)
------------------------------------------------------------
mood    : HPA/cortisol tone via ``taup`` (cortisol amplitude ~ 1/(1+taup))
hunger  : meal response width ``taug_vec`` and meal timing ``tM``
sleep   : cortisol tone ``taup`` + basal glucose ``B``
activity: activity pulses + pathway gains ``gamma_A, kappa_A, beta_A, eta_A, tau_A``
meals   : meal pattern ``tM``/``taug_vec``
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from scenariogen.descriptors import (
    DESCRIPTORS,
    DIMENSION_ORDER,
    descriptor_id,
)

# ---------------------------------------------------------------------------
# calibration (baseline) free-parameter set
# ---------------------------------------------------------------------------

# Matches the 'baseline' scenario in demos/py/scenarios.py plus engine
# defaults.  `pulses` is *not* an engine argument; precompute converts it to
# the activity signal A_raw via build_activity_signal().
CALIBRATION_PARAMS: dict = {
    "d": 1.0,
    "taup": 1.2,
    "B": 0.05,
    "Cm": 0.0,
    "toff": 0.0,
    "tM": (7.0, 11.0, 17.5),
    "taug_vec": (1.0, 1.0, 1.0),
    "pulses": (),
    "k_A": 5.0,
    "A_thresh": 0.3,
    "gamma_A": 0.15,
    "kappa_A": 0.5,
    "beta_A": 0.20,
    "eta_A": 0.40,
    "tau_A": 2.0,
}

PARAMETER_CATALOG: tuple[dict, ...] = (
    # name, description, default, is_free, domain
    {"param_name": "d", "description": "Circadian phase offset of the light/dark cycle (light peak ~ t=12+d)", "default_value": "1.0", "is_free": "true", "domain": "real; -2..4"},
    {"param_name": "taup", "description": "Cortisol tone: cortisol amplitude scales ~ 1/(1+taup); also shapes light signal sharpness", "default_value": "1.2", "is_free": "true", "domain": "real > 0"},
    {"param_name": "B", "description": "Bias constant scaling the basal glucose input term B*(1+meal_distr)", "default_value": "0.05", "is_free": "true", "domain": "real > 0"},
    {"param_name": "Cm", "description": "Circadian frequency multiplier of the meal distribution function cos^2(2*pi*Cm*(t+toff)/24)", "default_value": "0.0", "is_free": "true", "domain": "real >= 0"},
    {"param_name": "toff", "description": "Phase offset (hours) of the circadian meal distribution", "default_value": "0.0", "is_free": "true", "domain": "real; -12..12"},
    {"param_name": "tM", "description": "Meal onset times (hours of day, length = n_meals)", "default_value": "[7.0, 11.0, 17.5]", "is_free": "true", "domain": "list[real] 0..24"},
    {"param_name": "taug_vec", "description": "Meal duration widths (hours) per meal; taug_val used when empty", "default_value": "[1.0, 1.0, 1.0]", "is_free": "true", "domain": "list[real] > 0"},
    {"param_name": "pulses", "description": "Activity pulses [(center, width, amplitude)], converted to A_raw by build_activity_signal()", "default_value": "[]", "is_free": "true", "domain": "list[(h, h, 0..1)]"},
    {"param_name": "k_A", "description": "Activity activation slope of the sigmoid A = sigmoid(k_A*(A_raw-A_thresh))", "default_value": "5.0", "is_free": "true", "domain": "real > 0"},
    {"param_name": "A_thresh", "description": "Activity activation threshold of the sigmoid", "default_value": "0.3", "is_free": "true", "domain": "real 0..1"},
    {"param_name": "gamma_A", "description": "Contraction-mediated glucose uptake gain (delta_G_A = gamma_A*A/(1+kappa_A*A))", "default_value": "0.15", "is_free": "true", "domain": "real > 0"},
    {"param_name": "kappa_A", "description": "Contraction-mediated glucose uptake saturation", "default_value": "0.5", "is_free": "true", "domain": "real >= 0"},
    {"param_name": "beta_A", "description": "Activity modulation of cortisol (c_mod = c*(1+beta_A*A))", "default_value": "0.20", "is_free": "true", "domain": "real >= 0"},
    {"param_name": "eta_A", "description": "Post-exercise insulin sensitization gain (s_A recurrence)", "default_value": "0.40", "is_free": "true", "domain": "real >= 0"},
    {"param_name": "tau_A", "description": "Post-exercise insulin sensitization decay time constant (h)", "default_value": "2.0", "is_free": "true", "domain": "real > 0; <=0 disables"},
)


@dataclass(frozen=True)
class Override:
    """One deterministic parameter change caused by a descriptor."""

    descriptor_id: str
    param_name: str
    op: str            # 'set' | 'mul' | 'add'
    value: float | tuple
    rationale: str
    ref_id: str

    def apply(self, params: dict) -> None:
        current = params[self.param_name]
        if self.op == "set":
            params[self.param_name] = self.value
        elif self.op == "mul":
            if isinstance(current, tuple):
                params[self.param_name] = tuple(v * self.value for v in current)
            else:
                params[self.param_name] = current * self.value
        elif self.op == "add":
            if isinstance(current, tuple):
                params[self.param_name] = tuple(v + self.value for v in current)
            else:
                params[self.param_name] = current + self.value
        else:  # pragma: no cover - validated at construction
            raise ValueError(f"unknown op {self.op!r}")


# ---------------------------------------------------------------------------
# descriptors -> override rows
# ---------------------------------------------------------------------------

OVERRIDES: tuple[Override, ...] = (
    # ---- mood -----------------------------------------------------------
    Override(
        "mood:stressed", "taup", "mul", 0.633333333,
        "Chronic stress elevation of 24h cortisol output; modeled as +25% "
        "cortisol amplitude (amplitude ~ 1/(1+taup)). Static tone elevation: "
        "acute HPA spikes are not modeled.",
        "russell2019stress",
    ),
    Override(
        "mood:stressed", "taup", "mul", 1.0,
        "Elevated 24h cortisol in anxious/depressed states corroborates the "
        "tone-elevation channel.",
        "feder2004cortisol",
    ),
    Override(
        "mood:stressed", "B", "mul", 1.03,
        "Stress hyperglycemia raises the basal glucose level; simulation "
        "studies of stress hyperglycemia show elevated mean glucose.",
        "strilka2016stress",
    ),
    Override(
        "mood:tired", "taup", "mul", 0.818318318,
        "Sleepiness/fatigue correlates with raised cortisol and impaired "
        "glucose tolerance; modeled as +11% cortisol amplitude.",
        "vanleeuwen2010sleep",
    ),
    Override(
        "mood:tired", "B", "mul", 1.02,
        "Reduced glucose tolerance with sleep restriction raises fasting "
        "and overall glucose.",
        "vanleeuwen2010sleep",
    ),
    Override(
        "mood:happy", "taup", "mul", 1.181318681,
        "Positive affect is inversely correlated with daily cortisol "
        "output (happiest quintile ~32% lower cortisol); modeled as -9% "
        "cortisol amplitude (lower tone).",
        "steptoe2007affect",
    ),
    # ---- hunger ----------------------------------------------------------
    Override(
        "hunger:sated", "taug_vec", "mul", 0.90,
        "Expected satiety is represented by narrower glucose-response "
        "profiles; the engine has no direct meal-amplitude parameter.",
        "brunstrom2011satiety",
    ),
    Override(
        "hunger:hungry", "taug_vec", "mul", 1.08,
        "Larger meals are represented by broader glucose-response profiles; "
        "the engine has no direct meal-amplitude parameter.",
        "goldstone2009fasting",
    ),
    Override(
        "hunger:hungry", "taug_vec", "mul", 1.0,
        "Metabolic and hedonic drives increase meal size; this citation "
        "supports the appetite descriptor, while meal amplitude is not a "
        "separate engine parameter.",
        "berthoud2011appetite",
    ),
    Override(
        "hunger:starving", "taug_vec", "mul", 1.20,
        "Compensatory over-consumption after fasting is represented by "
        "broader glucose-response profiles; the engine has no direct "
        "meal-amplitude parameter.",
        "goldstone2009fasting",
    ),
    Override(
        "hunger:starving", "tM", "set", (6.5, 11.0, 17.5),
        "Fasting shortens the latency to the next meal (hippocampal "
        "meal-onset signaling); breakfast alone moves ~30 min earlier.",
        "henderson2013meal",
    ),
    # ---- sleep -----------------------------------------------------------
    Override(
        "sleep:poor", "taup", "mul", 0.848623853,
        "Sleep loss/fragmentation elevates cortisol and lowers glucose "
        "tolerance; modeled as +9% cortisol amplitude.",
        "vanleeuwen2010sleep",
    ),
    Override(
        "sleep:poor", "B", "mul", 1.02,
        "Reduced glucose tolerance raises basal glucose.",
        "vanleeuwen2010sleep",
    ),
    Override(
        "sleep:short", "taup", "mul", 0.720338983,
        "One week of 5h/night sleep restriction impairs glucose tolerance "
        "and insulin sensitivity; circadian misalignment reduces insulin "
        "sensitivity/secretion. Modeled as +18% cortisol amplitude.",
        "vanleeuwen2010sleep",
    ),
    Override(
        "sleep:short", "B", "mul", 1.04,
        "Sleep-restriction-induced insulin resistance approximates a "
        "fasting-hyperglycemia pattern.",
        "qian2018circadian",
    ),
    # ---- activity --------------------------------------------------------
    Override(
        "activity:light", "pulses", "set", ((12.5, 0.9, 0.18),),
        "A midday walk (AUC-matched to the light exercise literature on "
        "lowering postprandial glucose).",
        "shambrook2020walking",
    ),
    Override(
        "activity:light", "gamma_A", "set", 0.12,
        "Low-intensity contraction-mediated uptake gain.",
        "frampton2021exercise",
    ),
    Override(
        "activity:light", "beta_A", "set", 0.10,
        "Mild activity-induced cortisol modulation.",
        "frampton2021exercise",
    ),
    Override(
        "activity:light", "eta_A", "set", 0.35,
        "Modest post-exercise insulin sensitization for light activity.",
        "frampton2021exercise",
    ),
    Override(
        "activity:light", "tau_A", "set", 2.0,
        "Sensitization decays within hours for light exercise.",
        "sylow2017exercise",
    ),
    Override(
        "activity:moderate", "pulses", "set", ((6.75, 0.55, 0.55),),
        "Morning run pulse identical to the 'morning-run' demo scenario.",
        "frampton2021exercise",
    ),
    Override(
        "activity:moderate", "gamma_A", "set", 0.18,
        "Contraction-mediated uptake gain for moderate exercise.",
        "richter2013glut4",
    ),
    Override(
        "activity:moderate", "beta_A", "set", 0.15,
        "Moderate activity-induced cortisol modulation.",
        "frampton2021exercise",
    ),
    Override(
        "activity:moderate", "eta_A", "set", 0.55,
        "Larger post-exercise insulin sensitization.",
        "sylow2017exercise",
    ),
    Override(
        "activity:moderate", "tau_A", "set", 3.0,
        "Sensitization persists long after moderate exercise.",
        "richter2013glut4",
    ),
    Override(
        "activity:vigorous", "pulses", "set", ((6.75, 0.50, 0.85),),
        "Higher-intensity morning bout with larger activity signal.",
        "frampton2021exercise",
    ),
    Override(
        "activity:vigorous", "gamma_A", "set", 0.20,
        "Higher-intensity contraction-mediated uptake.",
        "frampton2021exercise",
    ),
    Override(
        "activity:vigorous", "beta_A", "set", 0.20,
        "Higher activity-induced cortisol modulation.",
        "frampton2021exercise",
    ),
    Override(
        "activity:vigorous", "eta_A", "set", 0.60,
        "Strong post-exercise insulin sensitization.",
        "sylow2017exercise",
    ),
    Override(
        "activity:vigorous", "tau_A", "set", 4.0,
        "Sensitization decays slowly after vigorous exercise.",
        "richter2013glut4",
    ),
    # ---- meal_schedule ---------------------------------------------------
    Override(
        "meal_schedule:skipped_breakfast", "tM", "set", (11.0, 17.5),
        "Breakfast omitted; first meal at 11:00 (two-meal protocol). Late "
        "first meal increases postprandial excursions.",
        "bandin2014meal",
    ),
    Override(
        "meal_schedule:skipped_breakfast", "taug_vec", "set", (1.4, 1.1),
        "Compensatory larger lunch/dinner after the skipped breakfast.",
        "henry2020chrono",
    ),
    Override(
        "meal_schedule:late_dinner", "tM", "set", (7.0, 11.0, 20.5),
        "Dinner delayed to 20:30; evening circadian phase is relatively "
        "unfavourable for glucose tolerance.",
        "zecevic2023timing",
    ),
    Override(
        "meal_schedule:late_dinner", "taug_vec", "set", (1.0, 1.0, 1.2),
        "A somewhat larger evening meal is represented by a broader "
        "glucose-response profile; there is no direct meal-amplitude "
        "parameter.",
        "bandin2014meal",
    ),
    Override(
        "meal_schedule:heavy_dinner", "tM", "set", (7.0, 11.0, 19.0),
        "Dinner at 19:00 with a disproportionately large evening meal.",
        "bandin2014meal",
    ),
    Override(
        "meal_schedule:heavy_dinner", "taug_vec", "set", (1.0, 1.0, 1.35),
        "Wider dinner glucose pulse encodes the larger evening meal size.",
        "monnier2003postprandial",
    ),
)

OVERRIDE_INDEX: dict[str, list[Override]] = {}
for _ov in OVERRIDES:
    OVERRIDE_INDEX.setdefault(_ov.descriptor_id, []).append(_ov)

# Provenance note: the value of the single-parameter 1.0 multiplier rows is
# intentionally neutral; they exist so that every descriptor has an explicit
# audit trail row per supporting reference (see override_ref_ids).


def overrides_for(desc_id: str) -> tuple[Override, ...]:
    """Return the override rows attached to a descriptor (empty if none)."""
    return tuple(OVERRIDE_INDEX.get(desc_id, ()))


def override_ref_ids(desc_id: str) -> tuple[str, ...]:
    """References cited by a descriptor's overrides (deduplicated)."""
    seen: list[str] = []
    for ov in overrides_for(desc_id):
        for ref in (ov.ref_id,):
            if ref not in seen:
                seen.append(ref)
    return tuple(seen)


def validate_overrides() -> None:
    """Raise if any override references an unknown descriptor or reference."""
    from scenariogen.references import REFERENCE_INDEX

    known = set(DESCRIPTORS)
    for ov in OVERRIDES:
        if ov.descriptor_id not in known:
            raise ValueError(f"unknown descriptor {ov.descriptor_id!r}")
        if ov.ref_id not in REFERENCE_INDEX:
            raise ValueError(
                f"override for {ov.descriptor_id} cites unknown ref {ov.ref_id!r}"
            )


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------


def resolve_params(descriptor_set: dict[str, str] | None = None) -> dict:
    """Resolve a descriptor combination into the full engine parameter dict.

    ``descriptor_set`` maps dimension id -> descriptor id (or label).  Missing
    dimensions fall back to that dimension's default descriptor.  Overrides
    are applied in ``DIMENSION_ORDER``, starting from CALIBRATION_PARAMS, so
    the result is deterministic.  The returned dict is a fresh copy; callers
    may mutate it freely.
    """
    if descriptor_set is None:
        descriptor_set = {}

    unknown_dims = set(descriptor_set) - set(DIMENSION_ORDER)
    if unknown_dims:
        raise ValueError(
            "unknown dimension(s) in descriptor set: "
            + ", ".join(sorted(unknown_dims))
        )

    params = deepcopy(CALIBRATION_PARAMS)

    for dim_id in DIMENSION_ORDER:
        if dim_id not in descriptor_set or not descriptor_set[dim_id]:
            continue
        raw = descriptor_set[dim_id]
        if ":" in raw:
            desc_id = raw
            # accept label form too (dimension inferred from the segment)
            dim, label = raw.split(":", 1)
            if dim != dim_id:
                raise ValueError(
                    f"descriptor {raw!r} does not belong to dimension {dim_id!r}"
                )
        else:
            desc_id = descriptor_id(dim_id, raw)
        if desc_id not in DESCRIPTORS:
            raise ValueError(f"unknown {dim_id} descriptor {raw!r}")

        for ov in overrides_for(desc_id):
            ov.apply(params)

    _finalize_tuples(params)
    return params


def resolve_default_params() -> dict:
    """Resolved parameter set of the all-default calibration scenario."""
    return resolve_params({})


def _finalize_tuples(params: dict) -> None:
    """Normalize tuple parameters to tuples of floats (dedupe 1.0 rows)."""
    for key in ("tM", "taug_vec"):
        params[key] = tuple(float(v) for v in params[key])
    params["pulses"] = tuple(
        (float(c), float(w), float(a)) for c, w, a in params["pulses"]
    )


def descriptor_parameter_effects() -> dict[str, list[dict]]:
    """Human/query-friendly list of effective changes per descriptor.

    Returns {descriptor_id: [{"param_name", "op", "value", "rationale",
    "ref_id"}]}; skips neutral rows (op=='mul' and value==1.0).
    """
    out: dict[str, list[dict]] = {}
    for ov in OVERRIDES:
        if ov.op == "mul" and abs(ov.value - 1.0) < 1e-12:
            continue
        out.setdefault(ov.descriptor_id, []).append(
            {
                "param_name": ov.param_name,
                "op": ov.op,
                "value": ov.value,
                "rationale": ov.rationale,
                "ref_id": ov.ref_id,
            }
        )
    return out


def run_simulation(descriptor_set: dict[str, str], t) -> dict:
    """Run the engine for a descriptor set, returning summary + arrays.

    Thin wrapper around :func:`scenariogen.db.engine_run`, imported lazily to
    avoid a circular import at module load time.
    """
    from scenariogen.db import engine_run

    out = engine_run(resolve_params(descriptor_set), t)
    return {"array": out, "summary": out["summary"]}


def compute_field_effects(descriptor_set: dict[str, str]) -> dict[str, float]:
    """Compare a descriptor set against the calibration run.

    Returns a dict of scenario-average summary fields (G_mean, G_max,
    I_E_eff_max, c_mean, A_peak) so callers can see the *direction* of the
    physiological perturbation without loading the full timecourse.  Internally
    this runs the engine at coarse resolution; use for previews only.
    """
    import numpy as np

    t = np.linspace(0.0, 24.0, 97)
    base = run_simulation({}, t)
    alt = run_simulation(descriptor_set, t)
    bs, as_ = base["summary"], alt["summary"]
    return {
        "G_mean_delta": as_["G_mean"] - bs["G_mean"],
        "G_max_delta": as_["G_max"] - bs["G_max"],
        "I_E_eff_max_delta": as_["I_E_eff_max"] - bs["I_E_eff_max"],
        "c_mean_delta": as_["c_mean"] - bs["c_mean"],
        "A_peak_delta": as_["A_peak"] - bs["A_peak"],
    }


validate_overrides()