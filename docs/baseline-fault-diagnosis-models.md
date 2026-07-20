# Baseline Fault-Diagnosis Models

This page describes the PR168 leakage-safe baseline model-evaluation
capability — the first supervised experiments run against the PR167
feature dataset. It assumes familiarity with
[Simulator Dataset Generation](simulator-dataset-generation.md) and
[Dataset Quality Audit](dataset-quality-audit.md); the feature dataset it
consumes (`features.parquet` + `labels.parquet` + `feature_manifest.json`)
is produced by `python -m backend.simulator.dataset.features` (PR167).

Like dataset generation and the quality audit, this is a parallel,
independent capability: it does not touch `src/domain` or
`src/application`, and nothing it produces feeds the deterministic
reasoning pipeline. There is no model deployment, calibration, streaming
inference, or MLflow integration here — this is an offline baseline
evaluation only.

---

## Running the experiment

```bash
pip install -e ".[ml]"   # scikit-learn + joblib, on top of pyarrow/numpy
python -m backend.simulator.dataset.models \
  --features datasets/pem-faults-pilot-features \
  --output datasets/pem-faults-pilot-models
```

`--dataset` optionally overrides the source dataset directory (used only
for evaluation-only metadata — configured fault severity, fault timing,
per-row `seconds_since_fault_start`); it defaults to
`feature_manifest.json`'s recorded `source_dataset.directory`.
`--overwrite` is required to replace an existing non-empty output
directory, matching every other generator in this package.

Output:

```
datasets/pem-faults-pilot-models/
├── experiment_summary.json   # every trial tried, selection, full results
├── evaluation_report.md      # human-readable report with the same content
├── metrics/
│   ├── validation_metrics.json
│   └── test_metrics.json
├── plots/                    # confusion matrix, ablation, severity, latency
└── artifacts/
    ├── selected_pipeline.joblib
    └── model_metadata.json
```

Generated model directories are **not** committed — `datasets/` is
git-ignored, same as generated dataset/feature/audit output.

---

## What gets trained and compared

Exactly two scikit-learn `Pipeline`s (`backend/simulator/dataset/models/pipelines.py`):

- **Logistic regression** — `StandardScaler` (train-split-only fit) +
  multinomial `LogisticRegression(class_weight="balanced")`. No imputer:
  `data.load_experiment_dataset` already rejects any non-finite value, so
  there is nothing for one to do.
- **Histogram gradient boosting** — `HistGradientBoostingClassifier`,
  unscaled, with sample weights (`pipelines.balanced_sample_weight`)
  standing in for the `class_weight` constructor argument it doesn't have.

Both are trained and validated across four feature-set ablations
(`backend/simulator/dataset/models/feature_groups.py`), each a strict
superset of the last:

| Group | Adds | Columns |
|---|---|---|
| A | Current raw telemetry only | 7 |
| B | + first differences/rates + trailing-window statistics | 147 |
| C | + cross-signal ratio features | 149 |
| D | + fixed-reference physics residuals (full feature set) | 153 |

A small, fixed hyperparameter grid (`config.LOGISTIC_REGRESSION_C_GRID`,
`config.HGB_HYPERPARAMETER_GRID`) is tried for every (model, feature-set)
combination — 32 configurations total, every one recorded in
`experiment_summary.json`'s `ablation.all_trials`, never just the winner.
Selection at every stage (hyperparameters, feature set, model, and the
row-level-to-run-level detection persistence policy) uses validation
balanced accuracy only; the test split is touched exactly once, after
every decision has already been made.

---

## Detection-event policy

A single anomalous row never counts as a detected fault
(`backend/simulator/dataset/models/detection.py`): the correct fault class
must be predicted for `N` consecutive samples (compared as `N=2` vs.
`N=3` on validation only, then fixed) before a run counts as detected.
Detection latency is the elapsed time from the run's configured fault
start to the first sample completing such a streak; a streak that starts
*before* the fault window opens never counts. The same persistence
mechanism, applied to genuinely healthy segments, produces the
false-alarms-per-healthy-hour operational metric.

---

## Operational and statistical-honesty reporting

Beyond standard multiclass metrics (balanced accuracy, macro/per-class
precision/recall/F1, confusion matrix), the report always includes:

- false-positive rate on healthy rows, false alarms per healthy simulated
  hour, missed-fault runs, and the percentage of fault runs detected
  within 30/60/120 seconds;
- per-class recall grouped by each run's **configured maximum** severity
  band (never the instantaneous ramped value — that would be evaluating
  against something closer to a feature) and by ramp-vs-post-ramp phase;
- run-level counts (not row counts) by split and class, since the
  independent experimental units are simulation runs — the pilot's
  validation/test splits carry only 4 target-fault runs per class, and
  the report flags any severity-band or detection-latency group backed by
  fewer than 3 runs rather than presenting it as a stable estimate;
- an optional run-level bootstrap interval for test balanced accuracy
  (`bootstrap.py`), resampling whole runs, never individual rows;
- an optional descriptive-only reference: the single best-measurement
  threshold rule from the PR166 audit's methodology, fit on the training
  split and evaluated on validation/test as a binary
  healthy-vs-anomalous baseline (never mixed into the ablation comparison
  above).

---

## Leakage protections

`data.load_experiment_dataset` (`backend/simulator/dataset/models/data.py`)
verifies, before any model ever sees the data:

- `feature_manifest.json`'s recorded file hashes match `features.parquet`
  and `labels.parquet` on disk;
- the manifest's `feature_columns` matches
  `features.schema.feature_column_order()` exactly (schema-version drift
  detection) and contains no forbidden field;
- **`features.parquet` and `labels.parquet` are not positionally
  aligned** — verified directly against the pilot dataset — so every row
  is joined explicitly by `(simulation_run_id, asset_id, timestamp)`,
  never assumed to match by position;
- no run ID's rows span more than one split;
- every feature value is finite.

Evaluation-only metadata (configured severity, fault timing,
`seconds_since_fault_start`) is read directly from the source dataset's
`runs.parquet`/`ground_truth.parquet` — never from the feature matrix —
mirroring `features/exclusions.py`'s distinction between legitimate
evaluation metadata and forbidden model features.

---

## Tests

`tests/backend/simulator/dataset/models/` covers: forbidden-column
rejection, manifest hash/order/split-overlap/row-alignment/non-finite
integrity checks against a real (physics-produced) tiny dataset; feature
ablation-group column correctness; multiclass metrics on hand-built
fixtures; severity-band and ramp/post-ramp grouping; the detection
persistence policy (exact-start, delayed, interrupted-streak, missed-run,
and no-detection-before-fault-start cases); train-only preprocessing fit;
deterministic reproducibility of a full experiment run; joblib
round-tripping of the selected pipeline; and one full end-to-end pilot-
style run asserting every required output artifact exists (not exact
metric values, which can shift across supported scikit-learn versions).

---

## Related documentation

- [Simulator Dataset Generation](simulator-dataset-generation.md)
- [Dataset Quality Audit](dataset-quality-audit.md)
- [Calibrated Confidence, Abstention, and Alert Policy](calibrated-confidence-and-alert-policy.md) —
  the PR169 decision layer built on this PR's selected model
- [Uncalibrated Temporal Alert-State Policy](uncalibrated-temporal-alert-policy.md) —
  the PR170 decision layer, built on this PR's native probabilities directly
- `backend/simulator/dataset/features/exclusions.py` — the forbidden-field
  policy this module's evaluation-metadata/feature-matrix boundary mirrors
