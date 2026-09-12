"""Health-metric descriptor dimensions and qualitative levels.

The scenario generator extends the physiology-backed CMA demo by exposing
*patient health metrics* as qualitative descriptors. Each descriptor is a
qualitative state on a categorical axis (e.g. ``mood=stressed``,
``hunger=starving``).  The mapping layer (``mapping.py``) translates each
descriptor into quantitative changes of the free parameters of the engine
(meal times/widths/load, circadian phase, cortisol tone, activity pathway),
so a full scenario is simply a *combination of one descriptor per dimension*.

Every descriptor carries a prose description and a physiological note that
names the mechanism channel used by the model (e.g. the HPA/cortisol axis is
accessed through the cortisol amplitude parameter ``taup``).  The supporting
peer-reviewed references live in ``references.py`` and are linked to
descriptors through ``descriptor_refs`` in the database.

Dimensions
----------
- ``mood``          affective state -> HPA/cortisol tone (taup), basal load (B)
- ``hunger``        appetitive state -> meal load (B, taug_vec) and timing (tM)
- ``sleep``         nocturnal sleep sufficiency -> cortisol tone (taup), basal glucose (B)
- ``activity``      daytime physical activity -> activity pulses + sensitization params
- ``meal_schedule`` meal timing/load pattern -> tM, taug_vec, B
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Descriptor:
    """A qualitative health-state level on one dimension."""

    descriptor_id: str          # e.g. 'mood:stressed'
    dimension_id: str           # e.g. 'mood'
    label: str                  # e.g. 'stressed'
    ordinal: int                # ordering within the dimension (0-based)
    description: str            # qualitative meaning
    physiological_note: str     # mechanism channel + modelling approximation


@dataclass(frozen=True)
class Dimension:
    """A categorical health-metric axis with an ordered set of descriptors."""

    dimension_id: str
    name: str
    description: str
    default_descriptor: str     # label of the reference state
    descriptors: tuple[Descriptor, ...]  # ordered by ordinal


# ---------------------------------------------------------------------------
# mood: affective state -> HPA / cortisol axis
# ---------------------------------------------------------------------------

_MOOD_DESCRIPTORS = (
    Descriptor(
        descriptor_id="mood:stressed",
        dimension_id="mood",
        label="stressed",
        ordinal=0,
        description=(
            "Acute/chronic psychosocial stress with elevated cortisol tone."
        ),
        physiological_note=(
            "Chronic stress raises 24 h cortisol output (Russell & Lightman "
            "2019; Feder et al. 2004), which suppresses insulin secretion "
            "(I_S = 1 - 0.23*c - 0.97*m) and raises fasting glucose. Modeled "
            "as a static elevation of cortisol amplitude via taup (amplitude "
            "~ 1/(1+taup)) plus a small rise of basal glucose B; acute "
            "stress spikes are NOT modeled (no feed-forward HPA dynamics)."
        ),
    ),
    Descriptor(
        descriptor_id="mood:tired",
        dimension_id="mood",
        label="tired",
        ordinal=1,
        description="Fatigue / low perceived energy.",
        physiological_note=(
            "Sleepiness and fatigue are associated with elevated cortisol "
            "and impaired glucose tolerance (van Leeuwen et al. 2010; Qian "
            "et al. 2018, circadian misalignment reduces insulin "
            "sensitivity). Modeled as increased cortisol tone (taup) with a "
            "small rise in basal glucose (B), approximating a mildly "
            "insulin-resistant state."
        ),
    ),
    Descriptor(
        descriptor_id="mood:neutral",
        dimension_id="mood",
        label="neutral",
        ordinal=2,
        description="Reference affective state (no mood perturbation).",
        physiological_note=(
            "Baseline HPA/cortisol tone; this is the calibration state of "
            "the model."
        ),
    ),
    Descriptor(
        descriptor_id="mood:happy",
        dimension_id="mood",
        label="happy",
        ordinal=3,
        description="Positive affect / hedonic wellbeing.",
        physiological_note=(
            "Positive affect is inversely correlated with daily cortisol "
            "output (Steptoe et al. 2007: the happiest quintile showed ~32% "
            "lower daily cortisol than the least happy). Modeled as a mild "
            "reduction of cortisol tone via taup. Only the cortisol channel "
            "is used; downstream reward/hedonic food choices are captured by "
            "the hunger dimension."
        ),
    ),
)

_MOOD = Dimension(
    dimension_id="mood",
    name="Mood / affect",
    description="Affective state implemented through the HPA/cortisol axis.",
    default_descriptor="neutral",
    descriptors=_MOOD_DESCRIPTORS,
)

# ---------------------------------------------------------------------------
# hunger: appetitive state -> meal load and timing
# ---------------------------------------------------------------------------

_HUNGER_DESCRIPTORS = (
    Descriptor(
        descriptor_id="hunger:sated",
        dimension_id="hunger",
        label="sated",
        ordinal=0,
        description="Low appetitive drive: appetite is satisfied.",
        physiological_note=(
            "Expected satiety reduces the amount eaten and lengthens the "
            "interval to the next meal (Brunstrom 2011; Berthoud 2011). "
            "Modeled as smaller meal loads (B down, taug_vec down)."
        ),
    ),
    Descriptor(
        descriptor_id="hunger:neutral",
        dimension_id="hunger",
        label="neutral",
        ordinal=1,
        description="Reference appetitive state (no hunger perturbation).",
        physiological_note=(
            "Baseline meal-driven glucose excursions (calibration state)."
        ),
    ),
    Descriptor(
        descriptor_id="hunger:hungry",
        dimension_id="hunger",
        label="hungry",
        ordinal=2,
        description="Elevated appetitive drive.",
        physiological_note=(
            "Metabolic and hedonic drives converge on larger meals and "
            "shorter inter-meal intervals (Berthoud 2011; Goldstone et al. "
            "2009: fasting biases reward towards high-calorie foods). "
            "Modeled as larger meal loads (B, taug_vec up)."
        ),
    ),
    Descriptor(
        descriptor_id="hunger:starving",
        dimension_id="hunger",
        label="starving",
        ordinal=3,
        description="Very high appetitive drive after prolonged fasting.",
        physiological_note=(
            "Prolonged fasting increases meal anticipation and biases intake "
            "towards energy-dense foods (Goldstone et al. 2009) and "
            "hippocampal meal-onset signaling shortens latencies to eat "
            "(Henderson et al. 2013; Parent et al. 2014). Modeled as larger, "
            "earlier meals (B and taug_vec up; breakfast shifted earlier)."
        ),
    ),
)

_HUNGER = Dimension(
    dimension_id="hunger",
    name="Hunger / appetite",
    description="Appetitive state implemented through meal load and timing.",
    default_descriptor="neutral",
    descriptors=_HUNGER_DESCRIPTORS,
)

# ---------------------------------------------------------------------------
# sleep: nocturnal sleep sufficiency -> cortisol tone + basal glucose
# ---------------------------------------------------------------------------

_SLEEP_DESCRIPTORS = (
    Descriptor(
        descriptor_id="sleep:poor",
        dimension_id="sleep",
        label="poor",
        ordinal=0,
        description="Fragmented or low-quality nocturnal sleep.",
        physiological_note=(
            "Sleep loss and fragmentation elevate evening cortisol and "
            "reduce glucose tolerance (van Leeuwen et al. 2010). Modeled as "
            "increased cortisol tone (taup) plus a small basal-glucose rise."
        ),
    ),
    Descriptor(
        descriptor_id="sleep:short",
        dimension_id="sleep",
        label="short",
        ordinal=1,
        description="Restricted sleep duration (e.g. ~5 h/night).",
        physiological_note=(
            "One week of 5 h/night sleep restriction impairs glucose "
            "tolerance and insulin sensitivity in healthy young men (van "
            "Leeuwen et al. 2010); circadian misalignment reduces insulin "
            "sensitivity and secretion (Qian et al. 2018; Morris et al. "
            "2015). Modeled as stronger cortisol tone and basal-glucose "
            "rises than 'poor' sleep."
        ),
    ),
    Descriptor(
        descriptor_id="sleep:restful",
        dimension_id="sleep",
        label="restful",
        ordinal=2,
        description="Reference sleep state (sufficient, restorative sleep).",
        physiological_note=(
            "Baseline cortisol rhythm and glucose tolerance (calibration "
            "state)."
        ),
    ),
)

_SLEEP = Dimension(
    dimension_id="sleep",
    name="Sleep sufficiency",
    description="Nocturnal sleep state implemented through cortisol and basal glucose.",
    default_descriptor="restful",
    descriptors=_SLEEP_DESCRIPTORS,
)

# ---------------------------------------------------------------------------
# activity: daytime physical activity -> activity pulses + sensitization
# ---------------------------------------------------------------------------

_ACTIVITY_DESCRIPTORS = (
    Descriptor(
        descriptor_id="activity:sedentary",
        dimension_id="activity",
        label="sedentary",
        ordinal=0,
        description="No structured physical activity during the day.",
        physiological_note=(
            "No activity pulses: A_raw = 0, so the contraction-mediated "
            "glucose uptake and post-exercise insulin sensitization "
            "pathways are silent (calibration state)."
        ),
    ),
    Descriptor(
        descriptor_id="activity:light",
        dimension_id="activity",
        label="light",
        ordinal=1,
        description="Light daytime movement, e.g. a midday walk.",
        physiological_note=(
            "Single bouts of aerobic exercise lower postprandial glucose "
            "(Frampton et al. 2021 meta-analysis); accumulating short walks "
            "improves glycaemic responses (Shambrook et al. 2020). Modeled "
            "as a small midday activity pulse with modest sensitization "
            "gain."
        ),
    ),
    Descriptor(
        descriptor_id="activity:moderate",
        dimension_id="activity",
        label="moderate",
        ordinal=2,
        description="Structured moderate exercise, e.g. a morning run.",
        physiological_note=(
            "A single moderate aerobic bout raises contraction-mediated "
            "glucose uptake (delta_G_A = gamma_A*A/(1+kappa_A*A)) and "
            "post-exercise insulin sensitization (Richter & Hargreaves 2013; "
            "Sylow et al. 2017; Frampton et al. 2021). Modeled as a morning "
            "pulse with the same shape as the 'morning-run' demo scenario."
        ),
    ),
    Descriptor(
        descriptor_id="activity:vigorous",
        dimension_id="activity",
        label="vigorous",
        ordinal=3,
        description="High-intensity exercise with sustained sensitization.",
        physiological_note=(
            "Higher-intensity bouts produce larger and longer-lasting "
            "insulin sensitization (Frampton et al. 2021; Richter & "
            "Hargreaves 2013). Modeled as a larger morning pulse with slower "
            "sensitization decay (larger tau_A)."
        ),
    ),
)

_ACTIVITY = Dimension(
    dimension_id="activity",
    name="Physical activity",
    description="Daytime physical activity implemented through the activity pathway.",
    default_descriptor="sedentary",
    descriptors=_ACTIVITY_DESCRIPTORS,
)

# ---------------------------------------------------------------------------
# meal_schedule: meal timing / load pattern
# ---------------------------------------------------------------------------

_MEAL_DESCRIPTORS = (
    Descriptor(
        descriptor_id="meal_schedule:standard",
        dimension_id="meal_schedule",
        label="standard",
        ordinal=0,
        description="Reference three-meal pattern (breakfast 7:00, lunch 11:00, dinner 17:30).",
        physiological_note=(
            "Baseline meal schedule of the calibration scenario."
        ),
    ),
    Descriptor(
        descriptor_id="meal_schedule:skipped_breakfast",
        dimension_id="meal_schedule",
        label="skipped_breakfast",
        ordinal=1,
        description="Breakfast omitted; first meal at ~11:00.",
        physiological_note=(
            "Meal timing alters glucose tolerance: a late first meal "
            "increases postprandial glucose excursions and shifts substrate "
            "oxidation (Bandín et al. 2014), and eating patterns are a "
            "chrononutrition lever in glucose management (Henry et al. "
            "2020). Modeled by dropping the breakfast meal (n_meals = 2) "
            "with a slightly larger lunch."
        ),
    ),
    Descriptor(
        descriptor_id="meal_schedule:late_dinner",
        dimension_id="meal_schedule",
        label="late_dinner",
        ordinal=2,
        description="Dinner delayed to ~20:30 (circadian-unfavourable window).",
        physiological_note=(
            "Late meals are less well tolerated because circadian control of "
            "glucose metabolism is relatively unfavourable in the evening "
            "(Kalsbeek et al. 2014; Zečević et al. 2023); endogenous "
            "circadian phase modulates the postprandial response (Morris et "
            "al. 2015). Modeled by shifting dinner to 20:30, which places "
            "the postprandial excursion in the low-cortisol evening window."
        ),
    ),
    Descriptor(
        descriptor_id="meal_schedule:heavy_dinner",
        dimension_id="meal_schedule",
        label="heavy_dinner",
        ordinal=3,
        description="Disproportionately large evening meal.",
        physiological_note=(
            "Meal-size distribution matters: large evening meals amplify "
            "nocturnal hyperglycaemia and fasting glucose the next morning "
            "(Monnier et al. 2003; Bandín et al. 2014). Modeled by a wider "
            "dinner glucose pulse (taug_vec[2] up) and a modest rise of "
            "basal glucose (B)."
        ),
    ),
)

_MEAL_SCHEDULE = Dimension(
    dimension_id="meal_schedule",
    name="Meal schedule",
    description="Meal timing and load pattern implemented through tM/taug_vec/B.",
    default_descriptor="standard",
    descriptors=_MEAL_DESCRIPTORS,
)

# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------

DIMENSIONS: dict[str, Dimension] = {
    dim.dimension_id: dim
    for dim in (_MOOD, _HUNGER, _SLEEP, _ACTIVITY, _MEAL_SCHEDULE)
}

DESCRIPTORS: dict[str, Descriptor] = {
    desc.descriptor_id: desc
    for dim in DIMENSIONS.values()
    for desc in dim.descriptors
}

DIMENSION_ORDER: tuple[str, ...] = (
    "mood",
    "hunger",
    "sleep",
    "activity",
    "meal_schedule",
)


def descriptor_id(dimension_id: str, label: str) -> str:
    """Return the canonical descriptor id for ``(dimension, label)``."""
    return f"{dimension_id}:{label}"


def default_descriptor_id(dimension_id: str) -> str:
    """Return the descriptor id of a dimension's reference state."""
    dim = DIMENSIONS[dimension_id]
    return descriptor_id(dimension_id, dim.default_descriptor)


def combinations(labels: bool = False) -> list[dict[str, str]]:
    """Cartesian product of all descriptor levels (one per dimension).

    Returns an ordered list of dicts mapping dimension -> descriptor id
    (or -> label when ``labels=True``).  The ordering is deterministic:
    dimensions follow ``DIMENSION_ORDER`` and within a dimension the levels
    follow their ordinal order, with the default level first per dimension.
    """
    import itertools

    levels: list[list[str]] = []
    for dim_id in DIMENSION_ORDER:
        dim = DIMENSIONS[dim_id]
        ordered = sorted(dim.descriptors, key=lambda d: d.ordinal)
        ordered.sort(key=lambda d: d.label != dim.default_descriptor)
        levels.append(
            [d.label if labels else d.descriptor_id for d in ordered]
        )
    out: list[dict[str, str]] = []
    for combo in itertools.product(*levels):
        out.append(dict(zip(DIMENSION_ORDER, combo)))
    return out


def core_combinations(labels: bool = False) -> list[dict[str, str]]:
    """Small 'core' buffer for clients that need only a few dozen scenarios:
    the all-default combination plus every single dimension perturbed to
    each of its non-default levels (1 + sum(len-1) entries)."""
    import itertools

    dims = [(d, DIMENSIONS[d]) for d in DIMENSION_ORDER]
    out: list[dict[str, str]] = []

    def build(perturbed_dim: str | None, level) -> dict[str, str]:
        combo: dict[str, str] = {}
        for dim_id, dim in dims:
            if dim_id == perturbed_dim:
                combo[dim_id] = level.label if labels else level.descriptor_id
            else:
                combo[dim_id] = (
                    dim.default_descriptor
                    if labels
                    else default_descriptor_id(dim_id)
                )
        return combo

    # all-default combination
    out.append(build(None, None))

    # every single-dimension perturbation (all non-default levels)
    for dim_id, dim in dims:
        for level in dim.descriptors:
            if level.label == dim.default_descriptor:
                continue
            out.append(build(dim_id, level))
    return out