# Calibrated Confidence, Abstention, and Alert Policy

This page describes the PR169 decision layer built on top of the
PR168-selected baseline model — sigmoid probability calibration, an
explicit `"uncertain"` abstention state, and a validation-selected
consecutive-persistence alert policy. It assumes familiarity with
[Baseline Fault-Diagnosis Models](baseline-fault-diagnosis-models.md);
the model this page calibrates is exactly PR168's selection (logistic
regression, feature set D, `C=0.01`) — no new model family, feature set,
or dataset changes.

Like the rest of this ML slice, this is a parallel, independent
capability: it does not touch `src/domain` or `src/application`, and
nothing it produces feeds the deterministic reasoning pipeline. There is
no deployment, streaming inference, drift monitoring, or MLflow
integration here — this is an offline decision-policy evaluation only.

---

## Running the experiment

```bash
pip install -e ".[ml]"
python -m backend.simulator.dataset.calibration \
  --features datasets/pem-faults-pilot-features \
  --output datasets/pem-faults-pilot-calibration
```

`--dataset` optionally overrides the source dataset directory (evaluation-
only metadata, same convention as `models`'s CLI). `--overwrite` is
required to replace an existing non-empty output directory.

Output:

```
datasets/pem-faults-pilot-calibration/
├── calibration_summary.json   # calibration metrics, coverage grid, PR168 comparison
├── policy_search.json         # every (threshold, persistence) candidate tried
├── uncertainty_report.md      # human-readable uncertainty breakdown
├── plots/                     # reliability diagram, confidence distribution,
│                               # coverage/accuracy and false-alarm/latency tradeoffs
└── artifacts/
    ├── calibrated_pipeline.joblib   # preprocessing + classifier + calibration, one object
    ├── decision_policy.json         # class order, threshold, persistence — everything
    │                                 # needed to *apply* the policy without re-deriving it
    └── model_card.md
```

Generated output is **not** committed — `datasets/` is git-ignored, same
as the dataset/feature/audit/model output it builds on.

---

## Calibration workflow (documented per the spec's own requirement)

The base pipeline is fit on the **training** split only — bit-for-bit
identical to PR168, never re-selected. The sigmoid (Platt-style)
calibrator is then fit on the **validation** split only, via
`sklearn.frozen.FrozenEstimator` wrapping the frozen base pipeline inside
`CalibratedClassifierCV`. This is "base on train, calibrated on
validation" — the simplest statistically honest option available, since
a validation split is already reserved for exactly this kind of
downstream-decision fitting.

**Why sigmoid, not isotonic**: the pilot's validation split has only 16
independent runs (12 fault + 4 healthy) backing ~5k highly-correlated
rows. Isotonic regression's nonparametric, many-degrees-of-freedom fit is
far more prone to overfitting that small an independent sample than
sigmoid's 2-parameters-per-class logistic fit — confirmed, not assumed,
during this PR's pre-implementation analysis.

**Caveat**: the validation-split "before/after" calibration metrics are
computed on the same rows the calibrator was fit on — informative for
comparison, not an independent holdout. The untouched test split is the
only true held-out check, evaluated exactly once after every decision
(calibration method, confidence threshold, persistence count) has already
been made.

---

## A finding worth knowing before reading the numbers

scikit-learn's multiclass sigmoid calibration fits an independent
one-vs-rest curve per class and then renormalizes — unlike binary Platt
scaling, this does **not** guarantee the argmax class is preserved. On
the pilot's test split, calibration alone (before any abstention) flips
the predicted class for about 10% of rows, dropping raw balanced accuracy
from PR168's 0.855 to about 0.77. Probabilities become dramatically
better calibrated (log loss, Brier score, and expected calibration error
all improve substantially) — but that is a *different* claim than
"classification got better," and the two must not be conflated. See
`calibration_classification_impact` in `calibration_summary.json` and
section 2 of `uncertainty_report.md`.

---

## Abstention and alert policy

A row is diagnosed only when its calibrated max-class probability meets
the selected confidence threshold; otherwise it is reported as
`"uncertain"` — never silently defaulted to `"healthy"`. A run-level
alert requires the same non-healthy, non-`"uncertain"` diagnosis for the
selected number of consecutive samples; an `"uncertain"` sample **breaks**
the sequence (never treated as healthy, never silently ignored) — the
spec's recommended, conservative choice for a first implementation.

Both the confidence threshold (from `{0.50, 0.60, 0.70, 0.80, 0.90}`) and
the persistence count (from `{2, 3, 4}`) are selected together via a
15-candidate grid search on validation, using a three-step rule
(`backend/simulator/dataset/calibration/config.py`'s
`SELECTION_RULE_DESCRIPTION`): reject any candidate missing more than 1 of
the validation split's 12 fault runs, minimize false alarms per healthy
hour among survivors, then tie-break by median latency and coverage.

---

## Tests

`tests/backend/simulator/dataset/calibration/` covers calibration safety
(train-only base fit, validation-only calibration fit, probabilities
summing to one, stable class ordering, deterministic refitting),
calibration-quality metrics on hand-built fixtures (log loss, Brier
score, expected calibration error, confidence bands), abstention
(threshold behavior, coverage metrics, healthy-false-positive vs.
uncertain-rate distinction), the alert policy (uncertain breaking the
consecutive sequence, exact-persistence detection, no pre-fault
detection, missed runs, false-alarm counting), policy search and
selection (missed-run cap enforcement, deterministic tie-breaking),
joblib/JSON serialization round-trips, and one full end-to-end pilot-
style run asserting every required output artifact exists.

---

## Related documentation

- [Baseline Fault-Diagnosis Models](baseline-fault-diagnosis-models.md)
- [Dataset Quality Audit](dataset-quality-audit.md)
