# Out-of-Distribution Evaluation (OOD v1)

This page describes PR171 — a strict, evaluation-only stress test of the
already-selected PR168 fault-diagnosis model and PR170 alert policy
against a deliberately shifted operating regime. It assumes familiarity
with [Baseline Fault-Diagnosis Models](baseline-fault-diagnosis-models.md)
and
[Uncalibrated Temporal Alert-State Policy](uncalibrated-temporal-alert-policy.md).

**The question this PR answers**: does the current fault-diagnosis and
alert system generalize to operating conditions it never saw during
training, without retraining, reselection, or threshold tuning? It is not
a model-development PR — no new model, feature, threshold, or calibration
decision is made here, and none of this PR's findings are used to revise
the frozen policy.

Like the rest of this ML slice, this is a parallel, independent
capability: it does not touch `src/domain` or `src/application`, and
nothing it produces feeds the deterministic reasoning pipeline. No Kafka,
API serving, frontend, or MLflow integration here.

---

## What stays fixed, what changes

**Fixed (loaded, never refit)**:

- Model: PR168's logistic-regression pipeline, full feature set D, `C=0.01`,
  `class_weight="balanced"` — loaded from `artifacts/selected_pipeline.joblib`.
- Alert policy: PR170's hysteresis state machine — entry probability 0.60,
  entry persistence 4, healthy-exit probability 0.50, exit persistence 2 —
  loaded from `artifacts/alert_policy.json`.
- Feature pipeline: the unmodified PR167 153-feature contract.

**Changed (the OOD v1 dataset only, `examples/dataset_specs/pem_faults_ood_v1.json`)**:

| Shift | Pilot (training) | OOD v1 |
|---|---|---|
| Baseline load | 50-70% | 68-82% |
| Load amplitude | 5-18% | 5-10% (narrowed — see below) |
| Initial stack-temperature offset | -3 to +3°C | +4 to +8°C |
| Fault onset | 90-420s | 500-600s |
| Sensor noise (5 core channels) | baseline | ~2x baseline stdev, same 3σ clip |
| Seeds | 1001-4016 | 11001-14016 (disjoint) |

**Why `load_amplitude_percent` is narrowed, not just shifted**: `OperatingConditions`
enforces `load_baseline_percent ± load_amplitude_percent` stays within
`[5, 95]`. Keeping the pilot's amplitude range (5-18%) at the OOD baseline
(68-82%) allows a sampled ceiling up to 100%, which would raise a
validation error at run-plan time. Narrowing amplitude to 5-10% keeps
every sampled combination valid (worst case: 82 + 10 = 92 ≤ 95) — the
smallest change that makes the requested load shift generatable at all.

**Why the fault-onset maximum is 600s, not 650s**: with a 240s ramp and a
900s run, a 650s onset leaves only a 10s fully-developed post-ramp window
— too little to say anything about post-ramp behavior. 600s leaves a 60s
(6-sample) post-ramp window instead, still short but usable, and stays on
the 10-second sampling grid.

Class/asset balance mirrors the pilot exactly: 16 runs per class,
round-robining evenly over the same 4 target assets (4 runs per
class/asset stratum, 64 runs total).

---

## Running the evaluation

```bash
pip install -e ".[ml]"

# 1. Generate the OOD dataset
python -m backend.simulator.dataset.generate \
  --spec examples/dataset_specs/pem_faults_ood_v1.json \
  --output datasets/pem-faults-ood-v1

# 2. Audit it with the unmodified PR166 audit
python -m backend.simulator.dataset.audit \
  --dataset datasets/pem-faults-ood-v1 \
  --output datasets/pem-faults-ood-v1-audit

# 3. Generate features with the unmodified PR167 pipeline
python -m backend.simulator.dataset.features \
  --dataset datasets/pem-faults-ood-v1 \
  --output datasets/pem-faults-ood-v1-features

# 4. Evaluate the frozen model + alert policy against it
python -m backend.simulator.dataset.ood \
  --training-features datasets/pem-faults-pilot-features \
  --ood-features datasets/pem-faults-ood-v1-features \
  --models datasets/pem-faults-pilot-models \
  --alert-policy datasets/pem-faults-pilot-alert-policy \
  --output datasets/pem-faults-ood-v1-evaluation
```

Output:

```
datasets/pem-faults-ood-v1-evaluation/
├── ood_evaluation_summary.json   # every metric, machine-readable
├── ood_evaluation_report.md      # human-readable report
├── feature_shift.json            # per-feature SMD/Wasserstein/out-of-range
├── error_cases.json              # representative-run timelines
└── plots/
    ├── ood_confusion_matrix.png
    ├── id_vs_ood_metrics.png
    ├── feature_shift_rankings.png
    ├── alert_latency_comparison.png
    └── representative_run_timelines.png
```

`--models`/`--alert-policy` point at directories in the same shape
`models`/`alert_policy` generate (`<dir>/artifacts/...`); `--training-dataset`/
`--ood-dataset` are optional overrides of the source dataset directory
recorded in each feature manifest.

---

## Frozen-artifact compatibility (`ood/artifacts.py`)

Loading fails loudly, never falls back to retraining, if:

- the pipeline or alert-policy file is missing;
- `model_metadata.json`'s `model_type`/`feature_group` isn't the frozen
  baseline (`logistic_regression` / `D`), or its `feature_columns` doesn't
  match `models.feature_groups.FEATURE_GROUPS["D"]`;
- its `source_feature_schema_version` doesn't match this codebase's
  `features.config.FEATURE_SCHEMA_VERSION`;
- `alert_policy.json`'s `class_order` doesn't match the pipeline's own
  fitted `classes_` order;
- `alert_policy.json` has no `state_machine_config` (no policy selected).

Class order is always read from `pipeline.named_steps["classifier"].classes_`
at load time, never assumed from `PRIMARY_CLASSES`' reporting order.

---

## A pipeline fragility the OOD shift exposed

`features.cross_signal.power_per_fuel_flow` is a documented
zero-denominator-null ratio feature. In the pilot dataset it is never
null. Under OOD v1's doubled sensor noise, `fuel_flow` occasionally clips
to exactly `0.0`, producing null `power_per_fuel_flow` on **206/20224
(1.0%)** OOD rows, scattered across 60/64 runs (mostly during low-load
moments, not concentrated in any one class). `sklearn`'s `StandardScaler`/
`LogisticRegression` cannot accept `NaN` at all, and this evaluation must
not invent an OOD-specific imputation. `ood/data_loading.py`'s loader
therefore **drops** (does not impute) any row with a null in this
documented-nullable column, raising immediately for a null anywhere else
(a genuine contract violation), and reports the drop count/breakdown
explicitly rather than silently shrinking the evaluated cohort. This is
itself an OOD finding, not a bug: a fixed, never-retrained feature
pipeline can develop new missing-data edge cases under a large enough
distribution shift.

---

## Results (pilot test split vs. OOD v1, whole cohort)

|  | ID (pilot test) | OOD v1 |
|---|---|---|
| Balanced accuracy | 0.855 | 0.580 |
| Healthy-row false-positive rate | 0.083 | 0.717 |
| False confirmed alert events/healthy-hour | 0.00 | 12.34 |
| Any-fault missed runs | 0 | 3 |
| Median correct-class latency | 165s | 130s |

The dominant failure mode: the model was trained almost entirely on
50-70% baseline load; at 68-82% it treats ordinary elevated-load healthy
operation as fault-like, driving the healthy-row false-positive rate from
8% to 72% and the false-alert rate from 0 to over 12 events per healthy
hour. Recall for the fault classes stays comparatively high (0.61-0.79)
— an actual fault is still further from "normal" than elevated-load
healthy operation is — but precision for `cooling_degradation` and
`hydrogen_supply_issue` collapses to ~0.05-0.07, because most of what gets
flagged as those classes is actually healthy high-load operation. See
`ood_evaluation_report.md` for the full per-class, per-severity-band, and
per-stage breakdown, and `feature_shift.json` for exactly which features
(mostly load-correlated trailing-window statistics) shifted furthest.

**Verdict: DOES NOT GENERALIZE — MODEL OR FEATURE REVISION REQUIRED**
(the false-alert rate alone exceeds the 5/healthy-hour "does not
generalize" threshold by more than 2x; see `ood/config.py` for every fixed
threshold and `ood/verdict.py` for the exact rule).

**Attribution caveat**: OOD v1 combines four shifts (load, initial
temperature, fault onset, sensor noise) simultaneously. The
feature-shift analysis and this report's narrative both point at the load
shift as the dominant driver, but that is an inference from which
features moved most, not a controlled, isolated result — no shift was
varied independently in this dataset.

---

## Interpreting degradation

Three verdicts, criteria fixed **before** looking at any OOD result
(`ood/config.py`):

- **GENERALIZES ACCEPTABLY**: balanced-accuracy drop ≤ 0.10, false-alert
  rate ≤ 1.0/healthy-hour, every class's any-fault missed-run fraction ≤ 0.25.
- **GENERALIZES WITH MATERIAL DEGRADATION**: useful performance remains,
  but does not meet the acceptable band and does not trigger collapse.
- **DOES NOT GENERALIZE**: any fault class's row recall ≤ 0.20, any
  class's any-fault missed-run fraction > 0.50, false-alert rate >
  5.0/healthy-hour, or OOD balanced accuracy ≤ 0.40.

---

## Limitations

- Only 16 runs per fault class — per-severity-band and per-stage recall
  breakdowns are indicative, flagged `small_sample` below
  `SMALL_GROUP_RUN_THRESHOLD` runs, never presented as statistically robust.
- This is simulator-only evidence from Plant Alpha's first-order-lag
  physics model, not a claim about a physical PEM fuel-cell plant.
- Combining four shifts in one dataset means no shift-level causal claim
  is directly supported (see the attribution caveat above).

---

## Tests

`tests/backend/simulator/dataset/ood/` covers: the committed OOD v1
specification (loads, plans all 64 runs, disjoint seeds, balanced
classes/assets, later-onset grid validity, doubled noise, shifted
operating ranges); frozen-artifact compatibility (every mismatch in
"Frozen-artifact compatibility" above, each independently rejected);
nullable-tolerant feature loading (matches the strict loader when nothing
is null, drops-and-reports a nullable-column null, still raises for a
non-nullable null, hash-mismatch rejection); feature-shift arithmetic
(zero shift for identical distributions, positive shift for shifted ones,
stable behavior for a constant feature, deterministic rankings); the
three-band verdict rule against directly constructed metric fixtures; and
an end-to-end smoke test on tiny generated datasets checking every output
artifact exists, all rows are accounted for (scored + dropped =
total), severity/stage breakdowns are present for every class, repeated
evaluation is byte-identical, and representative-case selection is
deterministic.

---

## Related documentation

- [Baseline Fault-Diagnosis Models](baseline-fault-diagnosis-models.md)
- [Calibrated Confidence, Abstention, and Alert Policy](calibrated-confidence-and-alert-policy.md)
- [Uncalibrated Temporal Alert-State Policy](uncalibrated-temporal-alert-policy.md)
