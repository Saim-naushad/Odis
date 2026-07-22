# AI Methodology

This page summarizes the full dataset-to-promotion narrative for ODIS's promoted
AI fault-diagnosis model — one page for a reviewer who wants the arc without reading
eleven PR-scoped documents. Each section links to the detailed page it summarizes;
this page adds no new claims beyond what's documented there.

**The short version:** a baseline model looked good in-distribution, failed hard
under distribution shift (specifically high sensor noise), was diagnosed, retrained
on a broader regime, and re-promoted only once evaluation proved the retrain actually
fixed the failure — not just that it looked different. A separate calibration attempt
was tried, made classification worse, and was explicitly not promoted. Both are real
findings, not hidden.

## 1. Dataset generation

[Simulator Dataset Generation](simulator-dataset-generation.md) · [Dataset Quality Audit](dataset-quality-audit.md)

- Plant Alpha simulator, 4 fault classes: `normal_operation`, `cooling_degradation`,
  `hydrogen_supply_issue`, `sensor_anomaly`.
- Pilot dataset: 64 runs (16/class), 900 simulated seconds/run, 10s sample interval,
  fault onset/duration/severity randomized per run.
- **Leakage-safe split**: run-level, stratified by `(class, target_asset)` — no run ID's
  rows span more than one split. Six automated audit checks (structural, labels,
  variation, physical, separability, 11-source leakage scan) gate every dataset version.

## 2. Feature engineering

[Numerically Safe Features](numerically-safe-features.md)

- 153 features (`FEATURE_SCHEMA_VERSION=1.0`), four ablation groups (A=7 raw →
  D=153 full, including cross-signal ratios and fixed-reference residuals).
- A numerical-safety pass (`safe_divide` with physically-motivated floors) replaced
  null-imputation with an explicit `insufficient_data` feature-rejection path — a
  divide-by-near-zero no longer silently becomes a wrong number.

## 3. Baseline models

[Baseline Fault Diagnosis Models](baseline-fault-diagnosis-models.md)

- 32 configurations compared (logistic regression vs. gradient boosting, × 4 feature
  sets, × hyperparameters), all recorded.
- Winner: **logistic regression, feature set D, `C=0.01`** — balanced accuracy **0.855**
  on the held-out test split (in-distribution).

## 4. A failed experiment: calibrated confidence

[Calibrated Confidence and Alert Policy](calibrated-confidence-and-alert-policy.md)

- Tried sigmoid (Platt) calibration to turn the model's raw scores into something closer
  to a real probability.
- **What broke**: multiclass sigmoid calibration is one-vs-rest + renormalize, which does
  not preserve which class had the highest raw score. On the test split it flipped the
  predicted class on **~10% of rows**, dropping balanced accuracy from **0.855 to ~0.77**.
  Calibration *metrics* (log loss, Brier, ECE) improved — but that's a different claim
  from "classification got better," and classification is what the alert policy depends on.
- **Not promoted.** This is why the alert policy (next section) is built on the model's
  native uncalibrated scores instead — and why every operator-facing response carries an
  explicit "uncalibrated diagnostic ranking, not a probability" caveat rather than
  presenting the score as confidence.

## 5. Alert policy (deterministic hysteresis, not calibration)

[Uncalibrated Temporal Alert Policy](uncalibrated-temporal-alert-policy.md)

- Instead of calibrating the score, PR170 reduces false alerts purely through temporal
  hysteresis on the native score — entry/exit thresholds each sustained for N samples —
  searched over a 72-candidate grid. This keeps row-level classification bit-for-bit
  identical to the baseline while cutting noise-driven flapping.
- The baseline policy (`C=0.01` model): entry probability 0.60 / persistence 4 samples,
  healthy-exit 0.50 / persistence 2 samples. (Superseded by the promoted policy below.)

## 6. Out-of-distribution failure

[Out-of-Distribution Evaluation](out-of-distribution-evaluation.md)

- Combined shift (load, amplitude, initial temperature, fault-onset timing, sensor
  noise) evaluated against the fixed baseline model+policy:

  | Metric | In-distribution | Combined OOD |
  |---|---|---|
  | Balanced accuracy | 0.855 | 0.580 |
  | Healthy-row false-positive rate | 0.083 | 0.717 |
  | False confirmed alerts / healthy-hour | 0.00 | 12.34 |
  | Any-fault missed runs | 0 | 3 |

- **Verdict: does not generalize — false-alert rate over 2x the acceptance threshold.**
  This finding is reported, not hidden — it's the reason the next two sections exist.

## 7. Isolating the root cause

[Isolated Shift Evaluation](isolated-shift-evaluation.md)

- Each shift dimension evaluated in isolation to find which one actually drove the
  combined failure:

  | Shift | Balanced accuracy | False alerts / healthy-hour |
  |---|---|---|
  | In-distribution | 0.855 | 0.00 |
  | high_load | 0.819 | 1.10 |
  | hot_start | 0.852 | 0.94 |
  | late_onset | 0.796 | 0.44 |
  | **high_noise** | **0.708** | **12.01** |
  | combined | 0.580 | 12.34 |

- **Diagnosis: sensor noise, not load or timing shift, was the dominant, near-solely
  responsible failure mode** (high_noise alone reproduces almost all of the combined
  false-alert rate). Recommended direction: broaden training coverage rather than
  change the model family or feature set.

## 8. Robust retraining and promotion

[Robustness Training](robustness-training.md)

- Retrained on 192 runs spanning a broadened operating envelope plus three sampled
  noise regimes per run (nominal / moderate / high_bounded), with fixed promotion
  criteria decided *before* looking at results (pilot accuracy can't drop more than
  0.03, high-noise accuracy must gain at least 0.02, false-alert rates must stay
  under 1.0/healthy-hour, no class recall below 0.20, ...).
- **PR174 candidate** (`C=10.0`, same feature set): meaningful gains everywhere,
  including high_noise (0.708 → 0.855, +0.146) and combined OOD (0.580 → 0.743,
  +0.163) — but high-noise false-alert rate only fell to 1.40/hr, still above the
  1.0 bound. **Decision at this point: keep the original model — robustness gains
  alone weren't sufficient**, the policy had to move too.
- **PR175** re-searched the alert policy for the new candidate (120-candidate grid)
  and selected entry probability 0.70 / persistence 4, healthy-exit 0.45 / persistence
  2 — this is the policy actually promoted. It cut high-noise false-alerts further to
  0.35/hr and pilot false-alerts to 0.0/hr. **Final decision: promote the retrained
  model and the new policy together.**

## 9. Final results — promoted system

| | |
|---|---|
| Model | Logistic regression, feature set D, `C=10.0` |
| Alert policy | Entry probability 0.70, persistence 4 samples; healthy-exit 0.45, persistence 2 samples |
| Feature schema | `FEATURE_SCHEMA_VERSION=1.0`, 153 features |
| Artifact bundle | `artifacts/models/plant_alpha_fault_v1/` (`pipeline.joblib`, `alert_policy.json`, `system_metadata.json`) |
| In-distribution balanced accuracy | 0.885 |
| High-noise balanced accuracy | 0.855 (was 0.708 pre-retrain) |
| Combined-OOD balanced accuracy | 0.743 (was 0.580 pre-retrain) |
| High-noise false-alert rate | 0.35/healthy-hour (was 12.01 pre-retrain) |

## 10. Runtime boundary

[Runtime Inference](runtime-inference.md) · [Kafka Fault Inference Worker](kafka-fault-inference-worker.md)

- The online `FaultInferenceSession` shares its exact feature-computation code with the
  offline training pipeline — no separate reimplementation to drift out of sync.
- Warm-up is exactly `LONGEST_WINDOW_SAMPLES=12` samples; the 12th sample is the first
  eligible prediction. Confirmed on a real live run: 11 consecutive `warming_up` results
  then `valid_prediction` at sample 12, `model_hash=30ae2bad5eca...067a8f`,
  `feature_schema_version=1.0` — re-confirmed live during this release's hardening pass
  (see [Release Scorecard](release/v1.1-scorecard.md)).
- Warm-up state is in-memory only; a worker restart resets it to zero.

## Limitations (carried forward honestly)

- Trained and evaluated entirely on simulator-generated data — no real-plant validation.
- Evaluation cohorts are simulator-scale (dozens to low hundreds of runs), not
  production traffic volumes.
- The model's native score is an uncalibrated ranking; the one attempt to calibrate it
  made classification worse and was not promoted.
- Distribution-shift robustness was validated for the specific shifts tested (load,
  timing, temperature, sensor noise); it is not a general robustness guarantee against
  unseen shift types.
- Deterministic reasoning remains the sole decision authority — this model never
  triggers an action on its own.
