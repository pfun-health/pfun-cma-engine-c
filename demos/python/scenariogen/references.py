"""Curated registry of peer-reviewed references backing the scenario generator.

Local-first policy
------------------
Before any web search, the reference list was mined from the local Zotero
library (``~/Zotero/zotero.sqlite``).  Each entry that exists locally carries
its ``zotero_item_id`` and - when a PDF attachment exists - the attachment
path inside the Zotero storage directory.  ``db.seed_references()`` can
optionally enrich this static registry directly from the live Zotero
database (exact authors, journal, DOI, absolute PDF path).

References that could NOT be found in the local library are marked with
``origin='web'`` and a DOI verified by web search:
- Steptoe et al. 2007 (positive affect and cortisol)        [doi:10.1016/j.psyneuen.2006.11.003]
- Richter & Hargreaves 2013 (exercise, GLUT4, glucose uptake) [doi:10.1152/physrev.00038.2012]
- Sylow et al. 2017 (exercise-stimulated glucose uptake)     [doi:10.1038/nrendo.2016.162]

Citation text follows the exact bibliographic records held locally.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reference:
    ref_id: str
    citation: str
    authors: str
    year: int | None
    title: str
    journal: str
    doi: str | None = None
    url: str | None = None
    zotero_item_id: int | None = None
    zotero_pdf_path: str | None = None   # path as recorded in Zotero (may be storage-relative)
    origin: str = "zotero"               # 'zotero' | 'web'


REFERENCES: tuple[Reference, ...] = (
    # --- mood / stress / HPA axis -----------------------------------------
    Reference(
        ref_id="russell2019stress",
        citation=(
            "Russell G, Lightman S. The human stress response. "
            "Nat Rev Endocrinol. 2019;15(9):525-534."
        ),
        authors="Russell G, Lightman S",
        year=2019, title="The human stress response",
        journal="Nature Reviews Endocrinology",
        doi="10.1038/s41574-019-0228-0",
        zotero_item_id=1572,
        zotero_pdf_path="storage:Russell_Lightman_2019_The human stress response.pdf",
    ),
    Reference(
        ref_id="feder2004cortisol",
        citation=(
            "Feder A, Coplan JD, Goetz RR, Mathew SJ, Pine DS, Dahl RE, "
            "Ryan ND, Greenwald S, Weissman MM. Twenty-four-hour cortisol "
            "secretion patterns in prepubertal children with anxiety or "
            "depressive disorders. Biol Psychiatry. 2004;56(3):198-204."
        ),
        authors=(
            "Feder A, Coplan JD, Goetz RR, Mathew SJ, Pine DS, Dahl RE, "
            "Ryan ND, Greenwald S, Weissman MM"
        ),
        year=2004, title=(
            "Twenty-four-hour cortisol secretion patterns in prepubertal "
            "children with anxiety or depressive disorders"
        ),
        journal="Biological Psychiatry",
        doi="10.1016/j.biopsych.2004.05.005",
        zotero_item_id=1599,
        zotero_pdf_path="storage:Feder et al. - 2004 - Twenty-four-hour cortisol secretion patterns in pr.pdf",
    ),
    Reference(
        ref_id="plat1996cortisol",
        citation=(
            "Plat L, Byrne MM, Sturis J, Polonsky KS, Mockel J, Féry F, "
            "Van Cauter E. Effects of morning cortisol elevation on insulin "
            "secretion and glucose regulation in humans. "
            "Am J Physiol. 1996;270(1):E36-E42."
        ),
        authors="Plat L, Byrne MM, Sturis J, Polonsky KS, Mockel J, Féry F, Van Cauter E",
        year=1996, title=(
            "Effects of morning cortisol elevation on insulin secretion and "
            "glucose regulation in humans"
        ),
        journal="American Journal of Physiology",
        doi="10.1152/ajpendo.1996.270.1.E36",
        zotero_item_id=1550,
    ),
    Reference(
        ref_id="strilka2016stress",
        citation=(
            "Strilka RJ, Stull M, Clemens M, McCaver S, Armen S. Simulation "
            "and qualitative analysis of glucose variability, mean glucose, "
            "and hypoglycemia after subcutaneous insulin therapy for stress "
            "hyperglycemia. Theor Biol Med Model. 2016;13:12."
        ),
        authors="Strilka RJ, Stull M, Clemens M, McCaver S, Armen S",
        year=2016, title=(
            "Simulation and qualitative analysis of glucose variability, "
            "mean glucose, and hypoglycemia after subcutaneous insulin "
            "therapy for stress hyperglycemia"
        ),
        journal="Theoretical Biology and Medical Modelling",
        doi="10.1186/s12976-016-0029-2",
        zotero_item_id=120,
        zotero_pdf_path=(
            "storage:Strilka et al_2016_Simulation and qualitative analysis "
            "of glucose variability, mean glucose, and.pdf"
        ),
    ),
    Reference(
        ref_id="petrowski2021light",
        citation=(
            "Petrowski K, Buehrer S, Niedling M, Schmalbach B. The effects "
            "of light exposure on the cortisol stress response in human "
            "males. Stress. 2021;24(1):29-35."
        ),
        authors="Petrowski K, Buehrer S, Niedling M, Schmalbach B",
        year=2021, title=(
            "The effects of light exposure on the cortisol stress response "
            "in human males"
        ),
        journal="Stress",
        doi="10.1080/10253890.2020.1741543",
        zotero_item_id=1535,
        zotero_pdf_path="storage:Petrowski et al. - 2021 - The effects of light exposure on the cortisol stre.pdf",
    ),
    Reference(
        ref_id="steptoe2007affect",
        citation=(
            "Steptoe A, Gibson EL, Hamer M, Wardle J. Neuroendocrine and "
            "cardiovascular correlates of positive affect measured by "
            "ecological momentary assessment and by questionnaire. "
            "Psychoneuroendocrinology. 2007;32(1):56-64."
        ),
        authors="Steptoe A, Gibson EL, Hamer M, Wardle J",
        year=2007, title=(
            "Neuroendocrine and cardiovascular correlates of positive "
            "affect measured by ecological momentary assessment and by "
            "questionnaire"
        ),
        journal="Psychoneuroendocrinology",
        doi="10.1016/j.psyneuen.2006.11.003",
        origin="web",
    ),
    Reference(
        ref_id="michael2018hpa",
        citation=(
            "Michael U, Oyesanya MO. Relating the effect of HPA axis to the "
            "emotional state of bipolar II disorder patient. "
            "Asian Res J Math. 2018;11(4):1-12."
        ),
        authors="Michael U, Oyesanya MO",
        year=2018, title=(
            "Relating the effect of HPA axis to the emotional state of "
            "bipolar II disorder patient"
        ),
        journal="Asian Research Journal of Mathematics",
        doi="10.9734/ARJOM/2018/44091",
        zotero_item_id=1598,
        zotero_pdf_path="storage:Michael and Oyesanya - 2018 - Relating the Effect of HPA Axis to the Emotional S.pdf",
    ),
    Reference(
        ref_id="dabney2020dopamine",
        citation=(
            "Dabney W, Kurth-Nelson Z, Uchida N, Starkweather CK, Hassabis D, "
            "Munos R, Botvinick M. A distributional code for value in "
            "dopamine-based reinforcement learning. Nature. 2020;577:671-675."
        ),
        authors="Dabney W, Kurth-Nelson Z, Uchida N, Starkweather CK, Hassabis D, Munos R, Botvinick M",
        year=2020, title=(
            "A distributional code for value in dopamine-based reinforcement "
            "learning"
        ),
        journal="Nature",
        doi="10.1038/s41586-019-1924-6",
        zotero_item_id=1360,
    ),
    Reference(
        ref_id="montague1996dopamine",
        citation=(
            "Montague PR, Dayan P, Sejnowski TJ. A framework for "
            "mesencephalic dopamine systems based on predictive Hebbian "
            "learning. J Neurosci. 1996;16(5):1936-1947."
        ),
        authors="Montague PR, Dayan P, Sejnowski TJ",
        year=1996, title=(
            "A framework for mesencephalic dopamine systems based on "
            "predictive Hebbian learning"
        ),
        journal="Journal of Neuroscience",
        doi="10.1523/JNEUROSCI.16-05-01936.1996",
        zotero_item_id=1386,
        zotero_pdf_path="storage:Montague et al. - 1996 - A framework for mesencephalic dopamine systems bas.pdf",
    ),
    # --- hunger / appetite / satiety --------------------------------------
    Reference(
        ref_id="brunstrom2011satiety",
        citation=(
            "Brunstrom JM, Brown S, Hinton EC, Rogers PJ, Fay SH. "
            "'Expected satiety' changes hunger and fullness in the "
            "inter-meal interval. Appetite. 2011;56(2):310-315."
        ),
        authors="Brunstrom JM, Brown S, Hinton EC, Rogers PJ, Fay SH",
        year=2011, title=(
            "'Expected satiety' changes hunger and fullness in the "
            "inter-meal interval"
        ),
        journal="Appetite",
        doi="10.1016/j.appet.2011.01.002",
        zotero_item_id=689,
    ),
    Reference(
        ref_id="berthoud2011appetite",
        citation=(
            "Berthoud HR. Metabolic and hedonic drives in the neural "
            "control of appetite: who is the boss? "
            "Curr Opin Neurobiol. 2011;21(6):888-896."
        ),
        authors="Berthoud HR",
        year=2011, title=(
            "Metabolic and hedonic drives in the neural control of appetite: "
            "who is the boss?"
        ),
        journal="Current Opinion in Neurobiology",
        doi="10.1016/j.conb.2011.09.004",
        zotero_item_id=807,
        zotero_pdf_path="storage:Berthoud - 2011 - Metabolic and hedonic drives in the neural control.pdf",
    ),
    Reference(
        ref_id="goldstone2009fasting",
        citation=(
            "Goldstone AP, Prechtl de Hernandez CG, Beaver JD, Muhammed K, "
            "Croese C, Bell G, Durighel G, Hughes E, Waldman AD, Frost G, "
            "Bell JD. Fasting biases brain reward systems towards "
            "high-calorie foods. Eur J Neurosci. 2009;30(8):1625-1635."
        ),
        authors=(
            "Goldstone AP, Prechtl de Hernandez CG, Beaver JD, Muhammed K, "
            "Croese C, Bell G, Durighel G, Hughes E, Waldman AD, Frost G, Bell JD"
        ),
        year=2009, title=(
            "Fasting biases brain reward systems towards high-calorie foods"
        ),
        journal="European Journal of Neuroscience",
        doi="10.1111/j.1460-9568.2009.06949.x",
        zotero_item_id=806,
        zotero_pdf_path="storage:Goldstone et al. - 2009 - Fasting biases brain reward systems towards high-c.pdf",
    ),
    Reference(
        ref_id="henderson2013meal",
        citation=(
            "Henderson YO, Smith GP, Parent MB. Hippocampal neurons inhibit "
            "meal onset. Hippocampus. 2013;23(1):100-107."
        ),
        authors="Henderson YO, Smith GP, Parent MB",
        year=2013, title="Hippocampal neurons inhibit meal onset",
        journal="Hippocampus",
        doi="10.1002/hipo.22062",
        zotero_item_id=682,
        zotero_pdf_path="storage:Henderson et al. - 2013 - Hippocampal neurons inhibit meal onset.pdf",
    ),
    Reference(
        ref_id="parent2014meal",
        citation=(
            "Parent MB, Darling JN, Henderson YO. Remembering to eat: "
            "hippocampal regulation of meal onset. "
            "Am J Physiol Regul Integr Comp Physiol. 2014;306(10):R701-R713."
        ),
        authors="Parent MB, Darling JN, Henderson YO",
        year=2014, title=(
            "Remembering to eat: hippocampal regulation of meal onset"
        ),
        journal=(
            "American Journal of Physiology-Regulatory, Integrative and "
            "Comparative Physiology"
        ),
        doi="10.1152/ajpregu.00496.2013",
        zotero_item_id=686,
        zotero_pdf_path="storage:Parent et al. - 2014 - Remembering to eat hippocampal regulation of meal.pdf",
    ),
    Reference(
        ref_id="hannapel2019hippocampus",
        citation=(
            "Hannapel RC, Ramesh J, Ross AE, LaLumiere RT, Roseberry AG, "
            "Parent MB. Postmeal optogenetic inhibition of dorsal or ventral "
            "hippocampal pyramidal neurons increases future intake. "
            "eNeuro. 2019;6(1):ENEURO.0457-18.2018."
        ),
        authors="Hannapel RC, Ramesh J, Ross AE, LaLumiere RT, Roseberry AG, Parent MB",
        year=2019, title=(
            "Postmeal optogenetic inhibition of dorsal or ventral "
            "hippocampal pyramidal neurons increases future intake"
        ),
        journal="eNeuro",
        doi="10.1523/ENEURO.0457-18.2018",
        zotero_item_id=803,
        zotero_pdf_path="storage:Hannapel et al. - 2019 - Postmeal Optogenetic Inhibition of Dorsal or Ventr.pdf",
    ),
    Reference(
        ref_id="james2004satiety",
        citation=(
            "James GA, Guo W, Liu Y. Interaction of satiety and reward "
            "response to food stimulation. J Addict Dis. 2004;23(3):23-37."
        ),
        authors="James GA, Guo W, Liu Y",
        year=2004, title=(
            "Interaction of satiety and reward response to food stimulation"
        ),
        journal="Journal of Addictive Diseases",
        doi="10.1300/J069v23n03_03",
        zotero_item_id=1020,
        zotero_pdf_path="storage:PhD et al. - 2004 - Interaction of Satiety and Reward Response to Food.pdf",
    ),
    Reference(
        ref_id="azevedo2019drd2",
        citation=(
            "Azevedo EP, Pomeranz L, Cheng J, Schneeberger M, Vaughan R, "
            "Stern S, Tan B, Doerig K, Greengard P, Friedman JM. A role of "
            "Drd2 hippocampal neurons in context-dependent food intake. "
            "Neuron. 2019;102(3):583-597."
        ),
        authors=(
            "Azevedo EP, Pomeranz L, Cheng J, Schneeberger M, Vaughan R, "
            "Stern S, Tan B, Doerig K, Greengard P, Friedman JM"
        ),
        year=2019, title=(
            "A role of Drd2 hippocampal neurons in context-dependent food "
            "intake"
        ),
        journal="Neuron",
        doi="10.1016/j.neuron.2019.03.011",
        zotero_item_id=1160,
        zotero_pdf_path="storage:Azevedo et al. - 2019 - A Role of Drd2 Hippocampal Neurons in Context-Depe.pdf",
    ),
    # --- sleep / circadian ------------------------------------------------
    Reference(
        ref_id="vanleeuwen2010sleep",
        citation=(
            "van Leeuwen WMA, Hublin C, Sallinen M, Härmä M, Hirvonen A, "
            "Porkka-Heiskanen T. Prolonged sleep restriction affects glucose "
            "metabolism in healthy young men. Int J Endocrinol. 2010;2010:108641."
        ),
        authors="van Leeuwen WMA, Hublin C, Sallinen M, Härmä M, Hirvonen A, Porkka-Heiskanen T",
        year=2010, title=(
            "Prolonged sleep restriction affects glucose metabolism in "
            "healthy young men"
        ),
        journal="International Journal of Endocrinology",
        doi="10.1155/2010/108641",
        zotero_item_id=1661,
        zotero_pdf_path="storage:van Leeuwen et al. - 2010 - Prolonged Sleep Restriction Affects Glucose Metabo.pdf",
    ),
    Reference(
        ref_id="qian2018circadian",
        citation=(
            "Qian J, Dalla Man C, Morris CJ, Cobelli C, Scheer FAJL. "
            "Differential effects of the circadian system and circadian "
            "misalignment on insulin sensitivity and insulin secretion in "
            "humans. Diabetes Obes Metab. 2018;20(10):2481-2485."
        ),
        authors="Qian J, Dalla Man C, Morris CJ, Cobelli C, Scheer FAJL",
        year=2018, title=(
            "Differential effects of the circadian system and circadian "
            "misalignment on insulin sensitivity and insulin secretion in "
            "humans"
        ),
        journal="Diabetes, Obesity and Metabolism",
        doi="10.1111/dom.13391",
        zotero_item_id=1579,
        zotero_pdf_path=(
            "storage:Qian et al_2018_Differential effects of the circadian "
            "system and circadian misalignment on.pdf"
        ),
    ),
    Reference(
        ref_id="morris2015circadian",
        citation=(
            "Morris CJ, Yang JN, Garcia JI, Myers S, Bozzi I, Wang W, "
            "Buxton OM, Shea SA, Scheer FAJL. Endogenous circadian system "
            "and circadian misalignment impact glucose tolerance via "
            "separate mechanisms in humans. Proc Natl Acad Sci USA. "
            "2015;112(17):E2225-E2234."
        ),
        authors=(
            "Morris CJ, Yang JN, Garcia JI, Myers S, Bozzi I, Wang W, "
            "Buxton OM, Shea SA, Scheer FAJL"
        ),
        year=2015, title=(
            "Endogenous circadian system and circadian misalignment impact "
            "glucose tolerance via separate mechanisms in humans"
        ),
        journal="Proceedings of the National Academy of Sciences",
        doi="10.1073/pnas.1418955112",
        zotero_item_id=1544,
        zotero_pdf_path="storage:Morris et al_2015_Endogenous circadian system and circadian misalignment impact glucose tolerance.pdf",
    ),
    Reference(
        ref_id="klerman2022circadian",
        citation=(
            "Klerman EB, Brager A, Carskadon MA, Depner CM, Foster R, "
            "Goel N, et al. Keeping an eye on circadian time in clinical "
            "research and medicine. Clin Transl Med. 2022;12(6):e1131."
        ),
        authors=(
            "Klerman EB, Brager A, Carskadon MA, Depner CM, Foster R, "
            "Goel N, Harrington M, Holloway PW, Knauert M, LeBourgeois M, "
            "Lipton J, Merrow M, Montagnese S, Ning M, Ray D, Scheer FAJL, "
            "Shea S, Skene DJ, Spies C, Staels B, St-Onge MP, Tiedt S, Zee P, Burgess H"
        ),
        year=2022, title=(
            "Keeping an eye on circadian time in clinical research and "
            "medicine"
        ),
        journal="Clinical and Translational Medicine",
        doi="10.1002/ctm2.1131",
        zotero_item_id=1542,
        zotero_pdf_path="storage:Klerman et al_2022_Keeping an eye on circadian time in clinical research and medicine.pdf",
    ),
    Reference(
        ref_id="stenvers2019circadian",
        citation=(
            "Stenvers DJ, Scheer FAJL, Schrauwen P, la Fleur SE, Kalsbeek A. "
            "Circadian clocks and insulin resistance. "
            "Nat Rev Endocrinol. 2019;15(2):75-89."
        ),
        authors="Stenvers DJ, Scheer FAJL, Schrauwen P, la Fleur SE, Kalsbeek A",
        year=2019, title="Circadian clocks and insulin resistance",
        journal="Nature Reviews Endocrinology",
        doi="10.1038/s41574-018-0122-1",
        zotero_item_id=156,
        zotero_pdf_path="storage:Stenvers et al. - 2019 - Circadian clocks and insulin resistance.pdf",
    ),
    Reference(
        ref_id="kalsbeek2014circadian",
        citation=(
            "Kalsbeek A, la Fleur SE, Fliers E. Circadian control of glucose "
            "metabolism. Mol Metab. 2014;3(4):372-383."
        ),
        authors="Kalsbeek A, la Fleur SE, Fliers E",
        year=2014, title="Circadian control of glucose metabolism",
        journal="Molecular Metabolism",
        doi="10.1016/j.molmet.2014.03.002",
        zotero_item_id=158,
        zotero_pdf_path="storage:Kalsbeek et al_2014_Circadian control of glucose metabolism.pdf",
    ),
    Reference(
        ref_id="bandin2014meal",
        citation=(
            "Bandín C, Scheer FAJL, Luque AJ, Ávila-Gandía V, Zamora S, "
            "Madrid JA, Gómez-Abellán P, Garaulet M. Meal timing affects "
            "glucose tolerance, substrate oxidation and circadian-related "
            "variables: a randomized, crossover trial. "
            "Int J Obes. 2015;39(5):828-833."
        ),
        authors=(
            "Bandín C, Scheer FAJL, Luque AJ, Ávila-Gandía V, Zamora S, "
            "Madrid JA, Gómez-Abellán P, Garaulet M"
        ),
        year=2014, title=(
            "Meal timing affects glucose tolerance, substrate oxidation and "
            "circadian-related variables: a randomized, crossover trial"
        ),
        journal="International Journal of Obesity",
        doi="10.1038/ijo.2014.182",
        zotero_item_id=128,
        zotero_pdf_path="storage:Bandín et al. - 2015 - Meal timing affects glucose tolerance, substrate o.pdf",
    ),
    Reference(
        ref_id="toffanin2013iob",
        citation=(
            "Toffanin C, Zisser H, Doyle FJ, Dassau E. Dynamic insulin on "
            "board: incorporation of circadian insulin sensitivity "
            "variation. J Diabetes Sci Technol. 2013;7(4):928-936."
        ),
        authors="Toffanin C, Zisser H, Doyle FJ, Dassau E",
        year=2013, title=(
            "Dynamic insulin on board: incorporation of circadian insulin "
            "sensitivity variation"
        ),
        journal="Journal of Diabetes Science and Technology",
        doi="10.1177/193229681300700415",
        zotero_item_id=1578,
        zotero_pdf_path="storage:Toffanin et al_2013_Dynamic Insulin on Board.pdf",
    ),
    Reference(
        ref_id="zecevic2023timing",
        citation=(
            "Zečević K, Popović N, Vuksanović Božarić A, Vukmirović M, "
            "Rizzo M, Muzurović E. Timing is important - management of "
            "metabolic syndrome according to the circadian rhythm. "
            "Biomedicines. 2023;11(4):1171."
        ),
        authors=(
            "Zečević K, Popović N, Vuksanović Božarić A, Vukmirović M, "
            "Rizzo M, Muzurović E"
        ),
        year=2023, title=(
            "Timing is important - management of metabolic syndrome "
            "according to the circadian rhythm"
        ),
        journal="Biomedicines",
        doi="10.3390/biomedicines11041171",
        zotero_item_id=1621,
        zotero_pdf_path="storage:Zečević et al. - 2023 - Timing Is Important—Management of Metabolic Syndro.pdf",
    ),
    Reference(
        ref_id="simonneaux2003melatonin",
        citation=(
            "Simonneaux V, Ribelayga C. Generation of the melatonin "
            "endocrine message in mammals: a review of the complex "
            "regulation of melatonin synthesis by norepinephrine, peptides, "
            "and other pineal transmitters. Pharmacol Rev. 2003;55(2):325-395."
        ),
        authors="Simonneaux V, Ribelayga C",
        year=2003, title=(
            "Generation of the melatonin endocrine message in mammals: a "
            "review of the complex regulation of melatonin synthesis by "
            "norepinephrine, peptides, and other pineal transmitters"
        ),
        journal="Pharmacological Reviews",
        doi="10.1124/pr.55.2.2",
        zotero_item_id=1555,
        zotero_pdf_path="storage:Simonneaux_Ribelayga_2003_Generation of the Melatonin Endocrine Message in Mammals.pdf",
    ),
    Reference(
        ref_id="garaulet2020melatonin",
        citation=(
            "Garaulet M, Qian J, Florez JC, Arendt J, Saxena R, Scheer FAJL. "
            "Melatonin effects on glucose metabolism: time to unlock the "
            "controversy. Trends Endocrinol Metab. 2020;31(3):192-204."
        ),
        authors="Garaulet M, Qian J, Florez JC, Arendt J, Saxena R, Scheer FAJL",
        year=2020, title=(
            "Melatonin effects on glucose metabolism: time to unlock the "
            "controversy"
        ),
        journal="Trends in Endocrinology & Metabolism",
        doi="10.1016/j.tem.2019.11.011",
        zotero_item_id=1543,
        zotero_pdf_path=(
            "storage:Garaulet et al_2020_Melatonin Effects on Glucose "
            "Metabolism.pdf"
        ),
    ),
    # --- meal timing / chrononutrition -------------------------------------
    Reference(
        ref_id="charlot2021trf",
        citation=(
            "Charlot A, Hutt F, Sabatier E, Zoll J. Beneficial effects of "
            "early time-restricted feeding on metabolic diseases: importance "
            "of aligning food habits with the circadian clock. "
            "Nutrients. 2021;13(5):1405."
        ),
        authors="Charlot A, Hutt F, Sabatier E, Zoll J",
        year=2021, title=(
            "Beneficial effects of early time-restricted feeding on "
            "metabolic diseases: importance of aligning food habits with "
            "the circadian clock"
        ),
        journal="Nutrients",
        doi="10.3390/nu13051405",
        zotero_item_id=1575,
        zotero_pdf_path="storage:Charlot et al_2021_Beneficial Effects of Early Time-Restricted Feeding on Metabolic Diseases.pdf",
    ),
    Reference(
        ref_id="henry2020chrono",
        citation=(
            "Henry CJ, Kaur B, Quek RYC. Chrononutrition in the management "
            "of diabetes. Nutr Diabetes. 2020;10(1):6."
        ),
        authors="Henry CJ, Kaur B, Quek RYC",
        year=2020, title=(
            "Chrononutrition in the management of diabetes"
        ),
        journal="Nutrition & Diabetes",
        doi="10.1038/s41387-020-0109-6",
        zotero_item_id=1576,
        zotero_pdf_path="storage:Henry et al. - 2020 - Chrononutrition in the management of diabetes.pdf",
    ),
    Reference(
        ref_id="monnier2003postprandial",
        citation=(
            "Monnier L, Lapinski H, Colette C. Contributions of fasting and "
            "postprandial plasma glucose increments to the overall diurnal "
            "hyperglycemia of type 2 diabetic patients: variations with "
            "increasing levels of HbA1c. Diabetes Care. 2003;26(3):881-885."
        ),
        authors="Monnier L, Lapinski H, Colette C",
        year=2003, title=(
            "Contributions of fasting and postprandial plasma glucose "
            "increments to the overall diurnal hyperglycemia of type 2 "
            "diabetic patients: variations with increasing levels of HbA1c"
        ),
        journal="Diabetes Care",
        doi="10.2337/diacare.26.3.881",
        zotero_item_id=3582,
    ),
    # --- activity / exercise ----------------------------------------------
    Reference(
        ref_id="frampton2021exercise",
        citation=(
            "Frampton J, Cobbold B, Nozdrin M, Oo H, Wilson H, Murphy KG, "
            "Frost GS, Chambers ES. The effect of a single bout of "
            "continuous aerobic exercise on glucose, insulin and glucagon "
            "concentrations compared to resting conditions in healthy "
            "adults: a systematic review, meta-analysis and meta-regression. "
            "Sports Med. 2021;51(7):1469-1484."
        ),
        authors=(
            "Frampton J, Cobbold B, Nozdrin M, Oo H, Wilson H, Murphy KG, "
            "Frost GS, Chambers ES"
        ),
        year=2021, title=(
            "The effect of a single bout of continuous aerobic exercise on "
            "glucose, insulin and glucagon concentrations compared to "
            "resting conditions in healthy adults: a systematic review, "
            "meta-analysis and meta-regression"
        ),
        journal="Sports Medicine",
        doi="10.1007/s40279-021-01473-2",
        zotero_item_id=1415,
        zotero_pdf_path="storage:Frampton et al. - 2021 - The Effect of a Single Bout of Continuous Aerobic .pdf",
    ),
    Reference(
        ref_id="shambrook2020walking",
        citation=(
            "Shambrook P, Kingsley MIC, Taylor NF, Wundersitz DW, "
            "Wundersitz CE, Paton CD, Gordon BA. A comparison of acute "
            "glycaemic responses to accumulated or single bout walking "
            "exercise in apparently healthy, insufficiently active adults. "
            "J Sci Med Sport. 2020;23(6):584-590."
        ),
        authors=(
            "Shambrook P, Kingsley MIC, Taylor NF, Wundersitz DW, "
            "Wundersitz CE, Paton CD, Gordon BA"
        ),
        year=2020, title=(
            "A comparison of acute glycaemic responses to accumulated or "
            "single bout walking exercise in apparently healthy, "
            "insufficiently active adults"
        ),
        journal="Journal of Science and Medicine in Sport",
        doi="10.1016/j.jsams.2020.02.015",
        zotero_item_id=1413,
        zotero_pdf_path="storage:Shambrook et al. - 2020 - A comparison of acute glycaemic responses to accum.pdf",
    ),
    Reference(
        ref_id="richter2013glut4",
        citation=(
            "Richter EA, Hargreaves M. Exercise, GLUT4, and skeletal muscle "
            "glucose uptake. Physiol Rev. 2013;93(3):993-1017."
        ),
        authors="Richter EA, Hargreaves M",
        year=2013, title=(
            "Exercise, GLUT4, and skeletal muscle glucose uptake"
        ),
        journal="Physiological Reviews",
        doi="10.1152/physrev.00038.2012",
        origin="web",
    ),
    Reference(
        ref_id="sylow2017exercise",
        citation=(
            "Sylow L, Kleinert M, Richter EA, Jensen TE. "
            "Exercise-stimulated glucose uptake - regulation and "
            "implications for glycaemic control. "
            "Nat Rev Endocrinol. 2017;13(3):133-148."
        ),
        authors="Sylow L, Kleinert M, Richter EA, Jensen TE",
        year=2017, title=(
            "Exercise-stimulated glucose uptake - regulation and "
            "implications for glycaemic control"
        ),
        journal="Nature Reviews Endocrinology",
        doi="10.1038/nrendo.2016.162",
        origin="web",
    ),
    # --- mathematical modelling / glucose forecasting ----------------------
    Reference(
        ref_id="palumbo2013model",
        citation=(
            "Palumbo P, Ditlevsen S, Bertuzzi A, De Gaetano A. Mathematical "
            "modeling of the glucose-insulin system: a review. "
            "Math Biosci. 2013;244(2):69-81."
        ),
        authors="Palumbo P, Ditlevsen S, Bertuzzi A, De Gaetano A",
        year=2013, title=(
            "Mathematical modeling of the glucose-insulin system: a review"
        ),
        journal="Mathematical Biosciences",
        doi="10.1016/j.mbs.2013.05.006",
        zotero_item_id=213,
        zotero_pdf_path="storage:Palumbo et al. - 2013 - Mathematical modeling of the glucose–insulin syste.pdf",
    ),
    Reference(
        ref_id="dallaman2007gim",
        citation=(
            "Dalla Man C, Raimondo D, Rizza R, Cobelli C. GIM, simulation "
            "software of meal glucose-insulin model. "
            "J Diabetes Sci Technol. 2007;1(3):323-330."
        ),
        authors="Dalla Man C, Raimondo D, Rizza R, Cobelli C",
        year=2007, title=(
            "GIM, simulation software of meal glucose-insulin model"
        ),
        journal="Journal of Diabetes Science and Technology",
        doi="10.1177/193229680700100303",
        zotero_item_id=119,
        zotero_pdf_path="storage:Dalla Man et al_2007_GIM, Simulation Software of Meal Glucose—Insulin Model.pdf",
    ),
    Reference(
        ref_id="rajagopalan2021gut",
        citation=(
            "Rajagopalan H, Lopez-Talavera JC, Klonoff DC, Cherrington AD. "
            "A gut-centric model of metabolic homeostasis. "
            "J Diabetes Sci Technol. 2021;15(6):1204-1211."
        ),
        authors="Rajagopalan H, Lopez-Talavera JC, Klonoff DC, Cherrington AD",
        year=2021, title=(
            "A gut-centric model of metabolic homeostasis"
        ),
        journal="Journal of Diabetes Science and Technology",
        doi="10.1177/19322968211044523",
        zotero_item_id=195,
        zotero_pdf_path="storage:Rajagopalan et al. - 2021 - A Gut-Centric Model of Metabolic Homeostasis.pdf",
    ),
    Reference(
        ref_id="albers2017forecast",
        citation=(
            "Albers DJ, Levine M, Gluckman B, Ginsberg H, Hripcsak G, "
            "Mamykina L. Personalized glucose forecasting for type 2 "
            "diabetes using data assimilation. "
            "PLoS Comput Biol. 2017;13(4):e1005232."
        ),
        authors=(
            "Albers DJ, Levine M, Gluckman B, Ginsberg H, Hripcsak G, "
            "Mamykina L"
        ),
        year=2017, title=(
            "Personalized glucose forecasting for type 2 diabetes using "
            "data assimilation"
        ),
        journal="PLOS Computational Biology",
        doi="10.1371/journal.pcbi.1005232",
        zotero_item_id=1422,
        zotero_pdf_path="storage:Albers et al. - 2017 - Personalized glucose forecasting for type 2 diabet.pdf",
    ),
    Reference(
        ref_id="vandoorn2021ml",
        citation=(
            "van Doorn WPTM, Foreman YD, Schaper NC, Savelberg HHCM, "
            "Koster A, van der Kallen CJH, et al. Machine learning-based "
            "glucose prediction with use of continuous glucose and physical "
            "activity monitoring data: the Maastricht Study. "
            "PLoS ONE. 2021;16(6):e0253125."
        ),
        authors=(
            "van Doorn WPTM, Foreman YD, Schaper NC, Savelberg HHCM, "
            "Koster A, van der Kallen CJH, Wesselius A, Schram MT, "
            "Henry RMA, Dagnelie PC, de Galan BE, Bekers O, Stehouwer CDA, "
            "Meex SJR, Brouwers MCGJ, Chen C"
        ),
        year=2021, title=(
            "Machine learning-based glucose prediction with use of "
            "continuous glucose and physical activity monitoring data: the "
            "Maastricht Study"
        ),
        journal="PLOS ONE",
        doi="10.1371/journal.pone.0253125",
        zotero_item_id=298,
        zotero_pdf_path="storage:van Doorn et al. - 2021 - Machine learning-based glucose prediction with use.pdf",
    ),
    Reference(
        ref_id="wijsman2013glucose",
        citation=(
            "Wijsman CA, van Heemst D, Hoogeveen ES, Slagboom PE, Maier AB, "
            "de Craen AJM, van der Ouderaa FJG, Pijl H, Westendorp RGJ, "
            "Mooijaart SP. Ambulant 24-h glucose rhythms mark calendar and "
            "biological age in apparently healthy individuals. "
            "Aging Cell. 2013;12(2):207-213."
        ),
        authors=(
            "Wijsman CA, van Heemst D, Hoogeveen ES, Slagboom PE, Maier AB, "
            "de Craen AJM, van der Ouderaa FJG, Pijl H, Westendorp RGJ, "
            "Mooijaart SP"
        ),
        year=2013, title=(
            "Ambulant 24-h glucose rhythms mark calendar and biological age "
            "in apparently healthy individuals"
        ),
        journal="Aging Cell",
        doi="10.1111/acel.12042",
        zotero_item_id=176,
        zotero_pdf_path="storage:Wijsman et al_2013_Ambulant 24-h glucose rhythms mark calendar and biological age in apparently.pdf",
    ),
    Reference(
        ref_id="macieak2020bmr" if False else "maciak2020bmr",
        citation=(
            "Maciak S, Sawicka D, Sadowska A, Prokopiuk S, Buczyńska S, "
            "Bartoszewicz M, Niklińska G, Konarzewski M, Car H. Low basal "
            "metabolic rate as a risk factor for development of insulin "
            "resistance and type 2 diabetes. "
            "BMJ Open Diabetes Res Care. 2020;8:e001381."
        ),
        authors=(
            "Maciak S, Sawicka D, Sadowska A, Prokopiuk S, Buczyńska S, "
            "Bartoszewicz M, Niklińska G, Konarzewski M, Car H"
        ),
        year=2020, title=(
            "Low basal metabolic rate as a risk factor for development of "
            "insulin resistance and type 2 diabetes"
        ),
        journal="BMJ Open Diabetes Research & Care",
        doi="10.1136/bmjdrc-2020-001381",
        zotero_item_id=123,
        zotero_pdf_path="storage:Maciak et al_2020_Low basal metabolic rate as a risk factor for development of insulin resistance.pdf",
    ),
    Reference(
        ref_id="lehman2015timeseries",
        citation=(
            "Lehman LH, Adams RP, Mayaud L, Moody GB, Malhotra A, Mark RG, "
            "Nemati S. A physiological time series dynamics-based approach "
            "to patient monitoring and outcome prediction. "
            "IEEE J Biomed Health Inform. 2015;19(1):1-11."
        ),
        authors=(
            "Lehman LH, Adams RP, Mayaud L, Moody GB, Malhotra A, Mark RG, "
            "Nemati S"
        ),
        year=2015, title=(
            "A physiological time series dynamics-based approach to patient "
            "monitoring and outcome prediction"
        ),
        journal="IEEE Journal of Biomedical and Health Informatics",
        doi="10.1109/JBHI.2014.2330827",
        zotero_item_id=446,
        zotero_pdf_path="storage:Lehman et al. - 2015 - A Physiological Time Series Dynamics-Based Approac.pdf",
    ),
    Reference(
        ref_id="steineck2019glucagon",
        citation=(
            "Steineck IIK, Ranjan AG, Schmidt S, Clausen TR, Holst JJ, "
            "Nørgaard K. Preserved glucose response to low-dose glucagon "
            "after exercise in insulin-pump-treated individuals with type 1 "
            "diabetes: a randomised crossover study. "
            "Diabetologia. 2019;62(4):582-590."
        ),
        authors=(
            "Steineck IIK, Ranjan AG, Schmidt S, Clausen TR, Holst JJ, "
            "Nørgaard K"
        ),
        year=2019, title=(
            "Preserved glucose response to low-dose glucagon after exercise "
            "in insulin-pump-treated individuals with type 1 diabetes: a "
            "randomised crossover study"
        ),
        journal="Diabetologia",
        doi="10.1007/s00125-018-4807-8",
        zotero_item_id=1416,
        zotero_pdf_path="storage:Steineck et al. - 2019 - Preserved glucose response to low-dose glucagon af.pdf",
    ),
    Reference(
        ref_id="finan2019glucagon",
        citation=(
            "Finan B, Capozzi ME, Campbell JE. Repositioning glucagon "
            "action in the physiology and pharmacology of diabetes. "
            "Diabetes. 2019;69(4):532-541."
        ),
        authors="Finan B, Capozzi ME, Campbell JE",
        year=2019, title=(
            "Repositioning glucagon action in the physiology and "
            "pharmacology of diabetes"
        ),
        journal="Diabetes",
        doi="10.2337/dbi19-0004",
        zotero_item_id=1418,
        zotero_pdf_path="storage:Finan et al. - 2019 - Repositioning Glucagon Action in the Physiology an.pdf",
    ),
    Reference(
        ref_id="kozawa2013glucagon",
        citation=(
            "Kozawa J, Okita K, Iwahashi H, Yamagata K, Imagawa A, "
            "Shimomura I. Early postprandial glucagon surge affects "
            "postprandial glucose levels in obese and non-obese patients "
            "with type 2 diabetes. Endocr J. 2013;60(6):813-821."
        ),
        authors=(
            "Kozawa J, Okita K, Iwahashi H, Yamagata K, Imagawa A, Shimomura I"
        ),
        year=2013, title=(
            "Early postprandial glucagon surge affects postprandial glucose "
            "levels in obese and non-obese patients with type 2 diabetes"
        ),
        journal="Endocrine Journal",
        doi="10.1507/endocrj.ej13-0018",
        zotero_item_id=1567,
        zotero_pdf_path="storage:Kozawa et al_2013_Early postprandial glucagon surge affects postprandial glucose levels in obese.pdf",
    ),
    Reference(
        ref_id="dsouza2017leptin",
        citation=(
            "D'souza AM, Neumann UH, Glavas MM, Kieffer TJ. The "
            "glucoregulatory actions of leptin. Mol Metab. 2017;6(9):1052-1065."
        ),
        authors="D'souza AM, Neumann UH, Glavas MM, Kieffer TJ",
        year=2017, title=(
            "The glucoregulatory actions of leptin"
        ),
        journal="Molecular Metabolism",
        doi="10.1016/j.molmet.2017.04.011",
        zotero_item_id=1547,
        zotero_pdf_path="storage:D'souza et al_2017_The glucoregulatory actions of leptin.pdf",
    ),
    Reference(
        ref_id="gavrila2003adiponectin",
        citation=(
            "Gavrila A, Peng CK, Chan JL, Mietus JE, Goldberger AL, "
            "Mantzoros CS. Diurnal and ultradian dynamics of serum "
            "adiponectin in healthy men: comparison with leptin, circulating "
            "soluble leptin receptor, and cortisol patterns. "
            "J Clin Endocrinol Metab. 2003;88(6):2838-2843."
        ),
        authors=(
            "Gavrila A, Peng CK, Chan JL, Mietus JE, Goldberger AL, "
            "Mantzoros CS"
        ),
        year=2003, title=(
            "Diurnal and ultradian dynamics of serum adiponectin in healthy "
            "men: comparison with leptin, circulating soluble leptin "
            "receptor, and cortisol patterns"
        ),
        journal="The Journal of Clinical Endocrinology & Metabolism",
        doi="10.1210/jc.2002-021721",
        zotero_item_id=1573,
        zotero_pdf_path="storage:Gavrila et al_2003_Diurnal and Ultradian Dynamics of Serum Adiponectin in Healthy Men.pdf",
    ),
)

REFERENCE_INDEX: dict[str, Reference] = {r.ref_id: r for r in REFERENCES}


def reference(ref_id: str) -> Reference:
    """Look up a reference by id (raises KeyError if unknown)."""
    return REFERENCE_INDEX[ref_id]