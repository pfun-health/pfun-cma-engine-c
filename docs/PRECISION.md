# CMA Engine Precision Assessment

## Result

| Boundary representation | Worst scaled absolute error | Worst-case scenario | Assessment |
|---|---:|---|---|
| FP32 | 6.221e-08 | activity_stress | Pass (limit 1e-06) |
| FP16 | 5.877e-04 | activity_stress | Fails (failure threshold 1e-04) |

Scaled absolute error is `max(abs(candidate - FP64 reference)) / max(1, max(abs(FP64 reference)))` for the signal and scenario.
FP32 is accepted here at a scaled error of at most `1e-6`; FP16 is considered inadequate when any measured signal exceeds `1e-4`.

## Per-signal worst cases

| Precision | Signal | Scenario | Max absolute error | Max scaled absolute error |
|---|---|---|---:|---:|
| FP32 | `G` | activity_stress | 1.193e-07 | 5.235e-08 |
| FP32 | `g` | baseline | 5.884e-08 | 4.921e-08 |
| FP32 | `I_E` | activity_stress | 2.976e-08 | 2.976e-08 |
| FP32 | `I_E_eff` | activity_stress | 3.493e-08 | 3.493e-08 |
| FP32 | `L` | activity_stress | 3.295e-08 | 3.295e-08 |
| FP32 | `m` | activity_stress | 4.854e-08 | 4.854e-08 |
| FP32 | `c` | activity_stress | 6.531e-08 | 5.809e-08 |
| FP32 | `c_mod` | activity_stress | 6.685e-08 | 4.958e-08 |
| FP32 | `A` | activity_stress | 6.221e-08 | 6.221e-08 |
| FP32 | `s_A` | activity_stress | 4.808e-08 | 4.808e-08 |
| FP32 | `a` | activity_stress | 2.995e-08 | 2.995e-08 |
| FP32 | `I_S` | activity_stress | 3.016e-08 | 3.016e-08 |
| FP16 | `G` | activity_stress | 1.073e-03 | 4.710e-04 |
| FP16 | `g` | baseline | 4.796e-04 | 4.011e-04 |
| FP16 | `I_E` | activity_stress | 2.479e-04 | 2.479e-04 |
| FP16 | `I_E_eff` | activity_stress | 3.195e-04 | 3.195e-04 |
| FP16 | `L` | activity_stress | 3.971e-04 | 3.971e-04 |
| FP16 | `m` | activity_stress | 4.344e-04 | 4.344e-04 |
| FP16 | `c` | activity_stress | 6.607e-04 | 5.877e-04 |
| FP16 | `c_mod` | activity_stress | 7.300e-04 | 5.414e-04 |
| FP16 | `A` | activity_stress | 4.150e-04 | 4.150e-04 |
| FP16 | `s_A` | activity_stress | 2.859e-04 | 2.859e-04 |
| FP16 | `a` | activity_stress | 2.840e-04 | 2.840e-04 |
| FP16 | `I_S` | activity_stress | 3.496e-04 | 3.496e-04 |

## Method and scope

- The reference is the current C engine, which evaluates its model using `double` values.
- At each candidate boundary, every numeric model input (including time arrays and parameters) is rounded to the indicated IEEE format, then widened to `double` for the existing engine call. Every output is rounded to that format before comparison.
- Scenarios cover a 24-hour baseline at 193 points and a 48-hour activity/stress case at 385 points. The model calls are deterministic and use no random seed.
- This measures input/output storage and transport precision; it does not emulate lower-precision arithmetic inside the model. Thus it supports FP32 boundary use under the stated error budget, rejects FP16 for that budget, and does not establish that internal FP32 arithmetic is safe.
- The error budget is a numerical engineering criterion, not a claim about physiological or clinical accuracy.

Regenerate with `make precision-report`. Acceptance checks run with `make test-precision`.
