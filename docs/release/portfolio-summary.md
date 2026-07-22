# ODIS v1.1 — Portfolio Summary

## One-line description

A deterministic industrial decision-intelligence platform for a simulated PEM
fuel-cell plant, where a promoted ML model raises candidate fault alerts that a
separate deterministic reasoning engine must independently corroborate before any
recommendation reaches an operator.

## Resume bullets

- Built a streaming AI-fault-diagnosis pipeline (Kafka telemetry → feature
  assembly → promoted logistic-regression model → temporal hysteresis alert
  policy → deterministic corroboration bridge) processing live simulator
  telemetry end to end with a verified 12-sample warm-up and idempotent
  Kafka-replay semantics (deterministic UUIDv5 event IDs, tested against
  duplicate delivery).
- Diagnosed and fixed a distribution-shift failure in the fault-diagnosis
  model — isolated sensor noise as the dominant root cause of a 12x false-alert
  spike under combined out-of-distribution shift, then retrained on a broadened
  operating envelope and re-searched the alert policy, cutting the high-noise
  false-alert rate from 12.01 to 0.35 per healthy-hour while improving
  in-distribution accuracy.
- Ran a full release-hardening audit of the platform (health/readiness,
  outbox delivery guarantees, event contracts, observability, demo
  reproducibility) and fixed the two most consequential findings: a silent
  Kafka-delivery data-loss bug in the transactional outbox, and a
  configuration gap that made the flagship AI-fault-alert feature unreachable
  from the project's own one-command demo — both verified fixed against a
  live Docker Compose stack, not just unit tests.

Each bullet describes work actually implemented and evaluated in this repository;
none references production traffic, real users, or real-world deployment — see
[Limitations](#limitations) below and the root [README](../../README.md).

## Interview explanation

### 30-second version

ODIS pairs a deterministic reasoning engine — evidence, signal, assessment,
decision, all explicit and replayable — with a promoted ML model that watches
streaming telemetry for fault patterns. The model can propose a fault; it can
never confirm one on its own. A separate deterministic corroboration step checks
the model's alert against real observations using explicit rules before anything
reaches an operator, and the operator-facing UI always shows the model's score
with an explicit "this is not a probability" caveat.

### 2-minute version

The system simulates a 4-stack PEM fuel-cell plant with real first-order-lag
physics (not RNG), publishes telemetry over Kafka and MQTT, and runs two parallel
decision paths on top of it. The original path is a seven-stage deterministic
reasoning pipeline — trend/variation detectors, evidence generation, hypothesis,
assessment, confidence scoring, explanation, planning — with no ML anywhere in
that chain. The newer path is a streaming ML pipeline: a Kafka consumer assembles
per-asset feature samples, runs a logistic-regression fault classifier trained
offline on leakage-safe simulator data, and applies a temporal-hysteresis alert
policy to avoid flapping on noisy single samples. When that policy confirms an
alert, a reasoning-bridge worker corroborates it against the platform's own
persisted observations using deterministic telemetry rules — the same kind of
explicit rule-based reasoning as the original pipeline — and only then does an
investigation reach the operator dashboard, complete with the corroborating rule
IDs and an explicit authority-boundary note. The model is evidence, not a verdict.

### Hardest engineering problem

Getting the model's evaluation honest was harder than getting a model that scored
well. An in-distribution baseline hit 0.855 balanced accuracy and looked done —
until an out-of-distribution stress test dropped it to 0.580 with a false-alert
rate 150x the acceptance threshold. Isolating *which* shift dimension caused that
(load, timing, temperature, or noise) required evaluating each one independently
rather than trusting the combined number, and the answer — sensor noise, almost
entirely — was not the one the first-pass analysis suggested. Fixing it meant
retraining on a broadened regime and *then* re-searching the alert policy for the
new model, because the retrain alone wasn't sufficient against the promotion
thresholds set before looking at results.

### One failed experiment and what changed

Tried calibrating the model's confidence score (sigmoid/Platt calibration) so it
would read as an honest probability instead of an opaque ranking. It measurably
improved calibration metrics (log loss, Brier score) — and simultaneously flipped
the predicted class on about 10% of test rows, because multiclass sigmoid
calibration is one-vs-rest-plus-renormalize and doesn't preserve which class had
the highest raw score. Balanced accuracy dropped from 0.855 to about 0.77. It was
not promoted. The alert policy that shipped instead reduces false alerts through
temporal hysteresis on the model's native uncalibrated score — and every
operator-facing response now says explicitly that the score is an uncalibrated
ranking, not a probability, rather than quietly implying otherwise.

### Why deterministic reasoning stayed authoritative

Because a model trained on simulator data, evaluated on a few hundred runs, will
be wrong sometimes in ways that don't show up in any offline metric — and an
operator acting on a wrong "confirmed fault" without any check is a worse failure
mode than an operator acting on a slightly-delayed but corroborated one. Keeping
a separate, auditable, rule-based corroboration step between the model and the
operator means every alert that reaches someone can be explained without
reference to the model's internals — "the deterministic rule that fired was X" is
a defensible sentence in a way that "the model was 91% confident" is not, given
that score isn't even a calibrated probability.

### What real deployment would require

Real plant telemetry to retrain and re-evaluate on (everything here is
simulator-generated); a calibration approach that doesn't break classification,
or a principled way to communicate an uncalibrated score to a human under time
pressure; durable (not in-memory) inference state across restarts; an atomic —
or at least reconciled — Kafka/HTTP delivery path instead of two independent
publishes; authentication and multi-tenancy; production-calibrated alert
thresholds and SLOs instead of the demo/reference ones shipped here; and a much
larger, more diverse evaluation cohort before any claim about real-world accuracy
would be honest.

## Limitations

Synthetic simulator data only; no real-plant validation; small evaluation
cohorts; uncalibrated model score; in-memory streaming-inference state; no
production security/SLO claim; no autonomous control. See root
[README](../../README.md) and [Release Scorecard](v1.1-scorecard.md) for the full,
current list.
