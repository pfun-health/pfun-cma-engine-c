from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class EvidenceNote:
    label: str
    rationale: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioDefinition:
    slug: str
    title: str
    summary: str
    tM: tuple[float, ...]
    taug_vec: tuple[float, ...]
    pulses: tuple[tuple[float, float, float], ...]
    k_A: float
    A_thresh: float
    gamma_A: float
    kappa_A: float
    beta_A: float
    eta_A: float
    tau_A: float
    evidence: tuple[EvidenceNote, ...]
    caveat: str | None = None
    d: float = 1.0
    taup: float = 1.2
    B: float = 0.05
    Cm: float = 0.0
    toff: float = 0.0


def build_activity_signal(
    t: np.ndarray, pulses: Iterable[tuple[float, float, float]]
) -> np.ndarray:
    signal = np.zeros_like(t, dtype=float)
    for center, width, amplitude in pulses:
        signal += amplitude * np.exp(-np.square((t - center) / width))
    return np.clip(signal, 0.0, 1.0)


def scenario_kwargs(defn: ScenarioDefinition, t: np.ndarray) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "t": t,
        "d": defn.d,
        "taup": defn.taup,
        "taug_val": float(np.mean(defn.taug_vec)),
        "taug_vec": np.asarray(defn.taug_vec, dtype=float),
        "B": defn.B,
        "Cm": defn.Cm,
        "toff": defn.toff,
        "tM": np.asarray(defn.tM, dtype=float),
        "seed": None,
        "eps": 1e-18,
        "A_raw": None,
        "k_A": defn.k_A,
        "A_thresh": defn.A_thresh,
        "gamma_A": defn.gamma_A,
        "kappa_A": defn.kappa_A,
        "beta_A": defn.beta_A,
        "eta_A": defn.eta_A,
        "tau_A": defn.tau_A,
    }
    if defn.pulses:
        kwargs["A_raw"] = build_activity_signal(t, defn.pulses)
    return kwargs


BASELINE_SCENARIO = ScenarioDefinition(
    slug="baseline",
    title="Baseline circadian + meals",
    summary="Reference day with breakfast, lunch, and dinner and no scheduled activity.",
    tM=(7.0, 11.0, 17.5),
    taug_vec=(1.0, 1.0, 1.0),
    pulses=(),
    k_A=5.0,
    A_thresh=0.3,
    gamma_A=0.15,
    kappa_A=0.5,
    beta_A=0.20,
    eta_A=0.40,
    tau_A=2.0,
    evidence=(),
)


MORNING_RUN_SCENARIO = ScenarioDefinition(
    slug="morning-run",
    title="Morning run",
    summary="Moderate aerobic run before breakfast with residual insulin sensitization through the morning.",
    tM=(8.0, 12.5, 18.5),
    taug_vec=(0.9, 1.0, 1.1),
    pulses=((6.75, 0.55, 0.55),),
    k_A=5.0,
    A_thresh=0.3,
    gamma_A=0.18,
    kappa_A=0.5,
    beta_A=0.15,
    eta_A=0.55,
    tau_A=3.0,
    evidence=(
        EvidenceNote(
            label="Run intensity and direct uptake",
            rationale=(
                "The activity pulse peaks at a pre-normalized intensity of 0.55 to represent a moderate run, "
                "which is strong enough to trigger contraction-mediated GLUT4 translocation without treating the session as maximal exercise. "
                "gamma_A is increased to 0.18 to make the acute glucose sink slightly stronger than the default sedentary configuration."
            ),
            sources=(
                "Richter EA, Hargreaves M. Exercise, GLUT4, and skeletal muscle glucose uptake. Physiol Rev. 2013;93(3):993-1017. PMID: 23899560.",
                "Lund S, Holman GD, Schmitz O, Pedersen O. Contraction stimulates translocation of glucose transporter GLUT4 in skeletal muscle through a mechanism distinct from that of insulin. Proc Natl Acad Sci U S A. 1995;92(13):5817-5821. PMID: 7597034.",
            ),
        ),
        EvidenceNote(
            label="Post-exercise insulin sensitivity",
            rationale=(
                "eta_A is raised to 0.55 and tau_A to 3.0 h so the model keeps a noticeable post-run insulin-sensitizing tail through breakfast and into lunch, "
                "matching the well-described several-hour acute improvement after one aerobic bout."
            ),
            sources=(
                "Cartee GD. Mechanisms for greater insulin-stimulated glucose uptake in normal and insulin-resistant skeletal muscle after acute exercise. Am J Physiol Endocrinol Metab. 2015;309(12):E949-E959. PMID: 26487009.",
                "Bird SR, Hawley JA. Update on the effects of physical activity on insulin sensitivity in humans. BMJ Open Sport Exerc Med. 2017;2(1):e000143. PMID: 28879003.",
                "Short KR, Pratt LV, Teague AM, et al. A single exercise session increases insulin sensitivity in normal weight and overweight/obese adolescents. Pediatr Diabetes. 2019;20(8):1073-1082. PMID: 30378106.",
            ),
        ),
        EvidenceNote(
            label="Counter-regulatory cortisol kept modest",
            rationale=(
                "beta_A is held to 0.15 so the run produces a visible but not dominant counter-regulatory cortisol bump; moderate aerobic exercise tends to raise cortisol once intensity passes a threshold, "
                "but the glucose-lowering effect of muscle uptake still predominates in short runs."
            ),
            sources=(
                "Hill EE, Zack E, Battaglini C, Viru M, Viru A, Hackney AC. Exercise and circulating cortisol levels: the intensity threshold effect. J Endocrinol Invest. 2008;31(7):587-591. PMID: 18787373.",
            ),
        ),
    ),
    caveat=(
        "This demo models the run as a glucose-disposal and short-lived sensitization event. The engine still has no explicit hepatic glucose production term, "
        "so prolonged fasting runs would overstate glucose lowering."
    ),
)


EVENING_PARTY_SCENARIO = ScenarioDefinition(
    slug="evening-party",
    title="Evening meal + party",
    summary="Later dinner followed by an immediate short walk and a longer block of light-to-moderate dancing.",
    tM=(7.5, 12.5, 19.0),
    taug_vec=(0.9, 1.0, 1.4),
    pulses=((19.35, 0.20, 0.22), (21.10, 0.90, 0.34)),
    k_A=5.0,
    A_thresh=0.3,
    gamma_A=0.12,
    kappa_A=0.5,
    beta_A=0.08,
    eta_A=0.30,
    tau_A=2.0,
    evidence=(
        EvidenceNote(
            label="Dinner is later and broader",
            rationale=(
                "The last meal is moved to 19:00 and its meal-width is lengthened to 1.4 h to emulate a larger evening eating window, because post-dinner glycemic excursions are often the hardest to control and often reflect the day's largest carbohydrate load."
            ),
            sources=(
                "Reynolds AN, Mann J, Williams S, Venn BJ. Advice to walk after meals is more effective for lowering postprandial glycaemia in type 2 diabetes mellitus than advice that does not specify timing: a randomised crossover study. Diabetologia. 2016;59(12):2572-2578. PMID: 27747394.",
                "DiPietro L, Gribok A, Stevens MS, Hamm LF, Rumpler W. Three 15-min bouts of moderate postmeal walking significantly improves 24-h glycemic control in older people at risk for impaired glucose tolerance. Diabetes Care. 2013;36(10):3262-3268. PMID: 23761134.",
            ),
        ),
        EvidenceNote(
            label="Immediate post-meal movement",
            rationale=(
                "A short low-amplitude pulse starts soon after dinner to represent the walk between the table and the party, because even brief post-meal ambulation reduces the dinner glucose excursion more effectively than the same activity done earlier in the day."
            ),
            sources=(
                "DiPietro L, Gribok A, Stevens MS, Hamm LF, Rumpler W. Three 15-min bouts of moderate postmeal walking significantly improves 24-h glycemic control in older people at risk for impaired glucose tolerance. Diabetes Care. 2013;36(10):3262-3268. PMID: 23761134.",
                "Reynolds AN, Mann J, Williams S, Venn BJ. Advice to walk after meals is more effective for lowering postprandial glycaemia in type 2 diabetes mellitus than advice that does not specify timing: a randomised crossover study. Diabetologia. 2016;59(12):2572-2578. PMID: 27747394.",
            ),
        ),
        EvidenceNote(
            label="Party dancing is moderate but less stressful than a run",
            rationale=(
                "The longer second pulse keeps activity in the light-to-moderate range, and gamma_A/beta_A/eta_A are all smaller than in the run scenario to reflect dancing that is metabolically helpful but usually less sustained and less cortisol-provoking than a continuous run."
            ),
            sources=(
                "Hargan K, Wilson J, Maclaren WM, et al. Efficacy of a culture-specific dancing programme to meet current physical activity recommendations in sedentary postmenopausal women. BMC Public Health. 2020;20:1112. PMID: 32784630.",
                "Hill EE, Zack E, Battaglini C, Viru M, Viru A, Hackney AC. Exercise and circulating cortisol levels: the intensity threshold effect. J Endocrinol Invest. 2008;31(7):587-591. PMID: 18787373.",
            ),
        ),
    ),
    caveat=(
        "The social activity is modeled as walking and dancing only. Alcohol is not encoded in the engine; peer-reviewed data show evening alcohol can increase delayed overnight or next-morning hypoglycemia risk, especially in diabetes."
    ),
)


SCENARIOS = {
    BASELINE_SCENARIO.slug: BASELINE_SCENARIO,
    MORNING_RUN_SCENARIO.slug: MORNING_RUN_SCENARIO,
    EVENING_PARTY_SCENARIO.slug: EVENING_PARTY_SCENARIO,
}
