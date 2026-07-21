# Deployable Inference Contract and Promoted Artifact Loader (PR176)

This page describes the runtime boundary future Kafka streaming and
API/dashboard work will call: `backend/simulator/inference/`, a small
package that loads the PR175-promoted fault-diagnosis system once,
accepts canonical observable telemetry for one asset over time, computes
the exact PR167/PR173 features incrementally, updates the PR170/PR175
alert state, and returns a typed, explainable result — with no dependency
on dataset Parquet files. It assumes familiarity with
[Baseline Fault-Diagnosis Models](baseline-fault-diagnosis-models.md),
[Numerically-Safe Features and Insufficient-Data Handling](numerically-safe-features.md),
[Uncalibrated Temporal Alert-State Policy](uncalibrated-temporal-alert-policy.md),
and [Robust Candidate Alert-Policy Selection](robustness-training.md).

This is evaluation/offline-to-online *bridge* work, not product
integration: no Kafka consumer/producer, FastAPI endpoint, database
persistence, dashboard UI, MLflow, or monitoring exists yet. Everything
here is a library other code will call next.

---

## Runtime artifact bundle

Generated files under `datasets/` are gitignored and not a reliable
deployment source — a fresh checkout has none of them. PR176 defines one
small, explicit runtime bundle directory instead:

```
artifacts/models/plant_alpha_fault_v1/
    pipeline.joblib          # the promoted sklearn Pipeline, unchanged bytes
    alert_policy.json        # {class_order, state_machine_config}
    system_metadata.json     # provenance + verification hashes (below)
```

**Repository policy**: this repo had already committed exactly one small
ML artifact directly — `backend/app/infrastructure/inference/models/
persistence_drift_v1.onnx` (439 bytes), a deliberate carve-out from the
`/datasets/` gitignore rule — and no `.joblib`/training artifact had ever
been committed before. The promoted pipeline here is ~10KB. Given that
precedent, and that no training dataset, feature dataset, or experiment
report is ever copied into it, `artifacts/models/plant_alpha_fault_v1/`
is a normal (not gitignored) path — small, immutable, and worth version-
controlling like the ONNX file was.

**Packaging** is one deterministic, verified copy step from PR175's own
promoted output (`datasets/pem-faults-robust-training-v1-policy/
artifacts/{promoted_pipeline.joblib, promoted_alert_policy.json,
promoted_system_metadata.json}`), never a re-derivation:

```bash
python -m backend.simulator.inference.bundle_cli \
    --source datasets/pem-faults-robust-training-v1-policy/artifacts \
    --output artifacts/models/plant_alpha_fault_v1 \
    --training-dataset-id pem-faults-robust-training-v1
```

`system_metadata.json` records: `system_version`, `model_hash`,
`policy_hash`, `metadata_hash` (a self-referential hash over every *other*
field, sorted-key JSON — detects any post-packaging edit to the metadata
file itself), `feature_schema_version`, `feature_order` (exact, ordered),
`class_order`, `safety_policy_version`, `training_dataset_id` +
`training_dataset_manifest_sha256` / `training_feature_manifest_sha256`,
`model_type`/`feature_group`/`hyperparameters`, `git_commit`, and the
original `promotion_decision`.

## Loader guarantees

`backend.simulator.inference.loader.load_promoted_fault_system(bundle_dir)`
is the one place runtime code ever loads the model+policy. It:

- rejects a bundle with a missing file (`PromotedArtifactNotFoundError`)
  or an unexpected extra file (`UnexpectedArtifactFileError`) — the
  contract is exactly three files, nothing more, nothing fewer;
- recomputes and verifies `metadata_hash`, `model_hash`, `policy_hash`;
- verifies `feature_order` against `models.feature_groups.FEATURE_GROUPS`,
  `feature_schema_version`/`safety_policy_version` against this
  codebase's current `FEATURE_SCHEMA_VERSION`, and `class_order` against
  the pipeline's own fitted `classes_`;
- verifies the loaded estimator's type name and its one swept
  hyperparameter (`C`, for logistic regression) match the metadata;
- **never retrains, never regenerates a missing file, and never silently
  substitutes a default** — every check raises a specific,
  `PromotedArtifactMismatchError`-family exception with an
  operator-actionable message.

The returned `PromotedFaultSystem` is a frozen dataclass; nothing about it
is mutated after loading.

## Telemetry input contract

`telemetry.TelemetrySample` is built from a batch of the domain's own
`Observation`/`MeasurementType` entities — not a bespoke parallel type —
via `TelemetrySample.from_observations(observations)`, the only validated
entry point. It represents exactly one asset at exactly one timestamp and
rejects: a duplicate measurement, a missing required measurement, an
unsupported measurement name, a unit that doesn't match the canonical
table below, a non-finite value, and (checked at the session, since it
needs a previous sample to compare against) a non-monotonic timestamp for
the same asset.

| measurement | canonical unit | required for features |
|---|---|---|
| `stack_temperature` | `celsius` | yes |
| `stack_pressure` | `kPa` | yes |
| `current` | `A` | yes |
| `voltage` | `V` | yes |
| `fuel_flow` | `SLPM` | yes |
| `power_output` | `kW` | yes |
| `coolant_flow` | `L/min` | yes |
| `efficiency` | `percent` | no (supported, not required — matches offline's own exclusion) |

A sample structurally cannot carry a label, fault metadata, simulation run
id, dataset id, scenario name, configured severity, or split — those
fields don't exist on `TelemetrySample`/`Observation` at all.

## Offline/online feature parity

This is the requirement PR176 treats as most important, and it is met by
**sharing code, not formulas**: `backend.simulator.dataset.features.row.
compute_feature_row` was extracted, without any formula change, from the
offline batch builder's per-row loop, and is now called identically by
both:

- `features.builder.build_feature_table` (batch, over a whole run's array
  and index), and
- `inference.session.FaultInferenceSession` (incremental, over a bounded
  per-measurement ring buffer capped at `LONGEST_WINDOW_SAMPLES` = 12
  entries, with the buffer's own last index playing the same role a
  batch row's index does).

Verified directly (`tests/backend/simulator/inference/
test_offline_online_parity.py`): for a real, physics-generated healthy
run and each of the three fault classes, the runtime session's diagnosed
class and class probabilities at every eligible timestamp match the
corresponding offline `features.parquet` row's own values, and a forced
near-zero `fuel_flow` sample is reported `insufficient_data` with the
exact same `near_zero_denominator` / `power_per_fuel_flow` reason the
offline `feature_rejections.parquet` contract would record.

The alert-state machine received the same treatment:
`alert_policy.state_machine.step_state_machine` was extracted from
`run_state_machine`'s per-row loop (a pure, behavior-preserving
refactor — the existing 38-test `test_state_machine.py` suite passes
unchanged), and the session calls it once per ingested sample, carrying
one small `AlertMachineState` value forward instead of replaying history.

**Elapsed-time convention**: like every offline run, feature and alert
computation are driven by a synthetic `elapsed_sim_seconds` clock that
advances by exactly `DT_SECONDS` (10s) per ingested sample — never by the
real gap between two samples' wall-clock timestamps, which is used only
to detect non-monotonic input and to stamp the result. The session
assumes, rather than measures, a fixed-cadence input stream — the same
assumption `features.builder.UnsupportedCadenceError` enforces offline.

## Warm-up, valid, and insufficient-data statuses

Every `ingest()` call returns one `result.InferenceResult`, discriminated
by `status`:

- **`warming_up`** — fewer than `LONGEST_WINDOW_SAMPLES` (12) samples
  ingested so far for this asset; `samples_available`/`samples_required`
  are set, `diagnosed_class` is `None`. Matches offline's own
  `index < LONGEST_WINDOW_SAMPLES - 1` warm-up drop exactly — the first
  eligible sample is the 12th.
- **`insufficient_data`** — every window is available, but at least one
  feature (currently only the two cross-signal ratios) could not be
  safely computed; `reason_codes`/`invalid_feature_names` are populated
  from the same `features.safety.FeatureRowValidity` object the offline
  builder uses, and `diagnosed_class` is `None` — **never reported as
  `healthy`**.
- **`valid_prediction`** — `diagnosed_class`, `class_probabilities`,
  `maximum_probability`, `alert_state`, `alert_event` (if one fired this
  sample), `evidence`, and the loaded system's `model_system_version`/
  `model_hash`/`policy_hash`/`feature_schema_version` are all populated.

## Alert-state semantics

Unchanged from PR170/PR175 (`healthy` / `pending_<class>` /
`confirmed_<class>`, entry/exit/class-switch hysteresis under the
promoted PR175 policy: entry probability 0.70, entry persistence 4,
healthy-exit probability 0.45, exit persistence 2). PR173's
`insufficient_data` semantics are preserved exactly: while `healthy`, an
insufficient-data row breaks any in-progress pending-confirmation streak;
while `confirmed_<C>`, it changes nothing (no counter advances, no event
fires). A confirmed-alert row-level model call never happens for an
insufficient-data row — feature computation fails before
`pipeline.predict_proba` is ever reached.

## Evidence

**Chosen approach: a small, curated, deterministic evidence set — not
SHAP, and not standardized-coefficient attribution.** Coefficient
attribution is explicitly allowed by the spec but requires exactly
reproducing the fitted `StandardScaler`'s per-feature mean/scale and the
classifier's per-class coefficients/intercepts/class-index mapping — a
second correctness-critical parity surface this PR does not need to open
just to explain a diagnosis. `evidence.build_evidence` returns at most 5
items, in a fixed, documented order: the diagnosed/top class's own
probability, the runner-up class's probability, the two physics-residual
features with the largest absolute magnitude (ties broken by name), and
alert entry/exit progress as a fraction of the persistence requirement —
every one of these is already computed as an ordinary part of inference,
nothing extra.

## Confidence semantics

`class_probabilities`/`maximum_probability` are the promoted logistic-
regression pipeline's native, **uncalibrated** `predict_proba` output —
useful for ranking classes and for the alert policy's own selected
threshold, but **not validated real-world likelihoods**. PR169's
calibration is not reintroduced here, and no calibrated-confidence claim
is made anywhere in this contract.

## Restart / state limitations

A `FaultInferenceSession`/`FaultInferenceManager` always starts cold —
warm-up history and alert state reset to their initial values on
construction, and `reset()` returns to that same cold start explicitly.
Cross-process state persistence/restoration is out of scope for this PR;
a future Kafka integration must decide whether to restore state (e.g.
from a compacted topic or a snapshot) or accept a restart's brief
warm-up/re-detection window. Neither type is thread-safe — one session
must only ever be driven by one caller at a time; a manager serving
multiple assets from multiple threads must synchronize externally.

## How Kafka will use this next

The intended shape for a future consumer: load one `PromotedFaultSystem`
per process at startup, keep one `FaultInferenceManager` for its
lifetime, and for each incoming message build a `TelemetrySample` (from
whatever wire format Kafka carries, converted to `Observation`s) and call
`manager.ingest(sample)`. Nothing in this PR assumes or requires a
particular transport — the manager's only inputs/outputs are the plain
dataclasses defined here.

## CLI smoke tool

```bash
python -m backend.simulator.inference \
    --artifact-dir artifacts/models/plant_alpha_fault_v1 \
    --telemetry datasets/pem-faults-pilot/telemetry.parquet \
    --run-id pem-faults-pilot-cooling_degradation-0000 \
    --asset-id fuel-cell-stack-01 \
    --offline-features datasets/pem-faults-pilot-features
```

Development validation only — never trains. Replays one `(run_id,
asset_id)` chronologically, printing every warm-up/prediction/alert-
transition/insufficient-data event, and (with `--offline-features`)
whether offline considered each timestamp eligible at all, as a quick
sanity signal during manual replay (the real, exact parity check lives in
the test suite, which has direct access to both sides).

## Tests

`tests/backend/simulator/inference/` covers: artifact loading (missing
file, unknown feature group, hash mismatches at every level, feature/
class-order mismatch, schema/safety-version mismatch, hyperparameter
mismatch, and a `Pipeline.fit`-patch proof of no retraining fallback);
telemetry validation (every rejection case, plus a structural proof the
contract carries no evaluation-only field); warm-up (no prediction before
the 12th sample, exact first-eligible-timestamp semantics, bounded
history); offline/online parity (healthy + all three fault classes +
the near-zero-denominator rejection, against a real generated dataset);
alert behavior (confirmation, no duplicate events while confirmed,
healthy exit, class switch, insufficient-data semantics — driven by a
scripted fake pipeline so these are tests of the *session's* wiring, not
of a tiny fixture model's incidental confidence); multi-asset isolation;
determinism (identical results and evidence order for a repeated
sequence); bundle packaging; and CLI smoke tests for both the replay tool
and the packaging tool.
