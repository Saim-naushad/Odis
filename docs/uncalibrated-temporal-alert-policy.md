# Uncalibrated Temporal Alert-State Policy

This page describes the PR170 decision layer — a deterministic hysteresis
state machine (`healthy` / `pending_<class>` / `confirmed_<class>`) built
directly on the PR168-selected model's **native, uncalibrated**
probabilities. It assumes familiarity with
[Baseline Fault-Diagnosis Models](baseline-fault-diagnosis-models.md) and,
for context on why it does *not* build on PR169 instead,
[Calibrated Confidence, Abstention, and Alert Policy](calibrated-confidence-and-alert-policy.md).

**Why not build on PR169's calibrated policy?** PR169 found that
multiclass sigmoid calibration changes ~10% of argmax predictions,
dropping row-level balanced accuracy from 0.855 to ~0.77 with slower
median detection latency. That makes PR169 a legitimate experimental
result, not a safe drop-in replacement for the PR168 baseline. PR170
instead reduces false alerts through temporal confirmation and exit
hysteresis alone — the underlying row-level predictions are never
touched, so row-level metrics stay bit-for-bit identical to PR168.

Like the rest of this ML slice, this is a parallel, independent
capability: it does not touch `src/domain` or `src/application`, and
nothing it produces feeds the deterministic reasoning pipeline. No Kafka,
API serving, frontend, or MLflow integration here.

---

## Running the experiment

```bash
pip install -e ".[ml]"
python -m backend.simulator.dataset.alert_policy \
  --features datasets/pem-faults-pilot-features \
  --output datasets/pem-faults-pilot-alert-policy
```

Output:

```
datasets/pem-faults-pilot-alert-policy/
├── alert_policy_search.json     # every (entry x persistence x exit) candidate tried
├── alert_evaluation_report.md   # human-readable report
├── plots/
└── artifacts/
    └── alert_policy.json        # decision-layer config only — references PR168's model,
                                   # never duplicates its serialized pipeline
```

No `.joblib` artifact is written here: PR170 reuses PR168's exact pipeline
unchanged, so `alert_policy.json` only records the state-machine
configuration and class ordering, plus a pointer to how to reproduce the
base model (`build_logistic_regression_pipeline(0.01)` on feature set D,
or PR168's own `selected_pipeline.joblib`).

---

## The state machine

Three states only — `healthy`, `pending_<class>`, `confirmed_<class>` —
per `(simulation_run_id, asset_id)`, reset fresh at the start of every run
(`backend/simulator/dataset/alert_policy/state_machine.py`):

- **Entry**: a candidate class begins tracking when a row's own argmax
  diagnosis is that class *and* its probability meets `entry_probability`.
  `entry_persistence` consecutive such rows confirm it and emit exactly
  one `new_alert` event — continued confirmed rows never emit duplicates.
- **Exit**: a *separate* counter tracks consecutive rows with
  `P(healthy) >= healthy_exit_probability`, independent of what the row's
  diagnosis is; `exit_persistence` consecutive such rows clears back to
  `healthy` and emits one `cleared` event.
- **Class switch**: while confirmed as `C`, a different class `C'` must
  independently satisfy its own `entry_persistence`-long streak before
  `confirmed_C -> confirmed_C'` fires as a `class_change` event — it does
  not wait for `C` to exit to `healthy` first. If both the exit streak and
  a switch-candidate streak complete on the same row, exit wins (a
  documented, conservative tie-break).

---

## Detection semantics

A pre-existing confirmed state that merely persists across fault onset,
with no post-onset transition, **does not** count as detection — spec
section 5's "prefer requiring a correct post-onset transition." This is
tracked explicitly (`confirmed_active_at_onset` /
`confirmed_class_at_onset`) rather than silently miscounted either way.
`correct_class_detected` and `any_fault_detected` are reported
separately, along with whether an incorrect class was confirmed before
the correct one.

---

## Policy search and selection

72 candidates (`entry_probability` × `entry_persistence` ×
`healthy_exit_probability` × `exit_persistence` = 4×3×3×2), all recorded.
Selection rule
(`backend/simulator/dataset/alert_policy/config.py`'s
`SELECTION_RULE_DESCRIPTION`):

1. reject any candidate missing more than 1 of the validation split's 12
   fault runs for correct-class detection;
2. reject any candidate whose median correct-class latency exceeds the
   PR168 N=3 row-sequence baseline's own (recomputed) median by more than
   30s;
3. among survivors, minimize false confirmed alert events per healthy
   simulated hour;
4. tie-break by fewer healthy runs affected, then shorter mean false-alert
   duration, then lower median latency, then the simplest policy.

If every candidate is rejected, `selected` is `None` and the report says
so explicitly — no forced fallback (unlike PR168/169's own policy search,
which always picks the least-bad candidate). Spec section 6 asks for this
honesty explicitly.

---

## A fair PR168 comparison

PR168's own "3 consecutive identical predictions" policy is recomputed
fresh (never hardcoded) under PR170's own episode/duration accounting, so
the false-alert-rate comparison is apples-to-apples rather than comparing
PR168's original row-persistence count against PR170's duration-aware
one.

---

## Tests

`tests/backend/simulator/dataset/alert_policy/` covers state transitions
(entry, exact-persistence confirmation, streak reset, no duplicate
events, exit hysteresis, class-switch persistence, isolated low-confidence
rows), event metrics (one continuous confirmation vs. two separated ones,
episode duration, healthy-hour normalization), detection (exact-start,
delayed, any-fault-before-correct-class, wrong-class-across-onset, missed
runs, pre-onset-confirmed-with-post-onset-transition), policy search
(missed-run and latency rejection, deterministic tie-breaking, a
structural signature check proving test-split data cannot reach the
selection function), reproducibility, and JSON round-tripping.

---

## Related documentation

- [Baseline Fault-Diagnosis Models](baseline-fault-diagnosis-models.md)
- [Calibrated Confidence, Abstention, and Alert Policy](calibrated-confidence-and-alert-policy.md)
