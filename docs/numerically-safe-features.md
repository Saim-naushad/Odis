# Numerically Safe Features and the Insufficient-Data Contract (PR173)

This page describes PR173 — a numerical-safety hardening pass on the
PR167 feature pipeline, triggered directly by
[PR172's isolated-shift study](isolated-shift-evaluation.md) finding that
`high_noise` alone drove a 1.90-2.43% feature-rejection rate (depending on
the exact denominator floor — see below), "too frequent for future online
inference." This is not a model-development PR: the frozen PR168 model
and PR170 alert policy are unchanged; only how the feature pipeline
handles numerically risky inputs, and how the frozen-evaluation and alert
layers consume that result, changed.

---

## Why this matters

Before PR173, exactly one feature family — the two cross-signal ratios,
`voltage_per_current` and `power_per_fuel_flow` — could produce a `null`
that survived into `features.parquet` (a documented, deliberate
zero-denominator guard). Every consumer downstream had to invent its own
tolerance for that null: PR171/PR172's `ood` evaluation module scanned
for it and dropped the row itself, `models.data.load_experiment_dataset`
raised outright. Neither is a real *contract* — there was no artifact
recording *why* a row was excluded, no reason code, no way to distinguish
"this timestamp is unscoreable" from "this timestamp is healthy" in a
downstream report. PR173 replaces ad hoc tolerance with one explicit,
central policy (`backend/simulator/dataset/features/safety.py`) and one
explicit artifact (`feature_rejections.parquet`).

## Numerical-risk audit

Every feature family was inspected for division by zero, near-zero-
denominator instability, overflow, non-finite results, and noise
amplification:

| Feature family | Formula | Risk | Disposition |
|---|---|---|---|
| Raw value | passthrough | none | — |
| First difference | `x_t - x_{t-1}` | none (subtraction of finite floats) | — |
| Rate of change | `diff / DT_SECONDS` | none — `DT_SECONDS=10.0` is a fixed constant, never zero | — |
| Rolling mean/min/max | `fmean`/`min`/`max` | none | — |
| Rolling std | `pstdev` (0.0 if 1 sample) | none | — |
| Rolling slope (OLS) | `Σ(x-x̄)(y-ȳ) / Σ(x-x̄)²` | zero variance only if <2 distinct timestamps in a window; structurally impossible given fixed 10s cadence and ≥3-sample windows | documented invariant, no code change |
| Rolling delta | `values[-1] - values[0]` | none | — |
| `voltage_per_current` | `voltage / current` | **`current` can clip to exactly 0.0 under sensor noise** (`sensor_noise.apply_sensor_noise`'s non-negative floor); near-zero current is also physically meaningless (startup/corrupted) | safe division, floor = 1.0A |
| `power_per_fuel_flow` | `power_output / fuel_flow` | **`fuel_flow` clips to 0.0 under doubled noise at low-load moments — the confirmed PR171/PR172 root cause** | safe division, floor = 0.1 SLPM |
| Fixed-reference residuals (×4) | `observed - reference_fn(current)` | `reference_fn` divides by a **fixed constant** (`_RATED_MAX_CURRENT_REF = 200.0`), never an observed value — no division risk. Residual magnitude can be large under extreme noisy `current`, but stays finite. | none |
| log/sqrt | not used anywhere in this feature set | n/a | n/a |

Only the two cross-signal ratios needed a policy change. Nothing else
divides by a live, noisy, physically-non-negative measurement.

## The safety policy (`features/safety.py`)

`safe_divide(numerator, denominator, *, min_abs_denominator, denominator_
name) -> SafeDivisionResult` is the single entry point every ratio
feature in this codebase routes through. Below `min_abs_denominator`, the
ratio is **not computed** — never substituted with an epsilon to produce
a large-but-meaningless finite value.

Two physically-motivated floors, chosen to be an order of magnitude below
the smallest value Plant Alpha's rated/healthy curve ever produces at its
lowest supported load — not statistically fit to any dataset:

| Ratio | Denominator | Floor | Why |
|---|---|---|---|
| `voltage_per_current` | `current` (A) | **1.0 A** | rated max current is 200A; even the lowest configured baseline load keeps steady-state current well above 50A |
| `power_per_fuel_flow` | `fuel_flow` (SLPM) | **0.1 SLPM** | base fuel flow at zero load is 1.5 SLPM; 0.1 is more than an order of magnitude below that |

`FeatureRowValidity` accumulates every feature's validity for one
timestamp as it's computed; a row with **any** invalid feature is
`insufficient_data`, carrying its reason codes, the specific invalid
feature names, and the triggering input value(s) — never silently
dropped, never imputed with an arbitrary zero.

This module is deliberately reusable by a future streaming/online
inference path: `safe_divide`/`FeatureRowValidity` take only plain
values, no batch-specific state, so a live sample and a Parquet batch row
get identical validity status and reason codes from the same code.

## The rejection contract

`build_feature_table` (features/builder.py) now writes two artifacts
instead of one:

- **`features.parquet`** — every column non-nullable (see
  `features/schema.py`). A row here is guaranteed fully finite.
- **`feature_rejections.parquet`** (new) — one row per excluded
  timestamp: `dataset_id`, `simulation_run_id`, `asset_id`, `timestamp`,
  `elapsed_sim_seconds`, `reason_codes` (list), `invalid_feature_names`
  (list, parallel to `reason_codes`), `diagnostic_values_json` (the
  triggering input value(s), e.g. `{"fuel_flow": 0.0747}`).

`labels.parquet` only ever contains rows for the valid set — alignment
with `features.parquet` is unaffected by rejection.

`feature_manifest.json` gained `row_counts.valid_rows`/`rejected_rows`,
`rejection_rate`, `rejection_counts_by_reason`, and
`rejection_counts_by_feature`. `eligible_rows` now means "passed warm-up,
attempted" (valid + rejected combined) rather than "became a feature
row" — the more accurate reading of "eligible," and unchanged in value
for any dataset with zero rejections.

**Schema compatibility**: the 153-feature column contract (names, order)
is unchanged — `FEATURE_SCHEMA_VERSION` stays `"1.0"`. Only the row-
inclusion criterion changed (a rejected row that used to appear with one
null column is now entirely absent from `features.parquet`), so no
existing model artifact's `source_feature_schema_version` check needed to
change, and no retraining was required to consume this PR's output.

## Frozen-evaluation and alert-policy consumption

`ood.data_loading.load_ood_experiment_dataset` no longer invents its own
row-dropping logic. Since `features.parquet` is now always fully finite,
it delegates entirely to PR168's own strict
`models.data.load_experiment_dataset`, and separately loads
`feature_rejections.parquet` into an `InsufficientDataSummary` (renamed
from PR171's `UnscoreableRowSummary`, since "insufficient data" is the
accurate description now that rejection is an explicit contract rather
than an inferred nullable-column workaround).

**Row-level diagnosis**: insufficient-data rows were never in the scored
`ExperimentDataset` to begin with, so they were never counted as a
correct or incorrect class prediction — unchanged from PR171/PR172's
behavior, just now backed by an explicit artifact instead of inferred
nullability.

**Alert-state behavior** (`alert_policy.state_machine.run_state_machine`,
extended with an optional `row_valid` sequence — `None`/all-`True`
reproduces PR170's exact original behavior byte-for-bit):

- while `healthy`: an insufficient-data row **breaks** any in-progress
  pending-confirmation streak.
- while `confirmed_<C>`: the confirmed state is **preserved unchanged**;
  neither the exit-persistence counter nor any switch-candidate streak
  advances (frozen, not reset) for that row.
- no event is ever emitted for an insufficient-data row itself.

This policy is deliberately conservative: bad input can neither manufacture
nor silently clear an alert. `ood.gapped_alert_evaluation` builds the
merged (valid rows + rejected-row placeholders, correctly time-ordered)
sequence per run and replays it through the unchanged PR170 event/episode
logic (`alert_policy.detection.evaluate_run_detection`, extended with the
same optional `row_valid` passthrough; `alert_policy.event_metrics.
episodes_from_events`, reused unmodified) — because gathering rows from a
loaded dataset *plus* a separate rejections file is a genuinely different
input contract than the original mask-based gathering, not a behavior
change to it.

## Metrics: model accuracy vs. operational availability, always both

`ood.availability_metrics.AvailabilityMetrics` is reported *alongside*,
never *instead of*, row-level diagnosis/alert metrics: valid-feature
coverage, insufficient-data rate/total duration, longest consecutive
insufficient-data streak, affected runs/assets, reason counts, the
rejected rows' ground-truth class and ramp/post-ramp stage distribution,
the fraction of all ramp/post-ramp timestamps that were unavailable, and
the count of fault-scenario runs whose detection window was interrupted
by at least one insufficient-data row.

---

## Results

Regenerating features with the new policy (same 153-column contract, no
retraining) on the pilot and both key OOD cohorts:

| Dataset | Rejected / eligible | Rate | Longest streak |
|---|---|---|---|
| Pilot (normal noise) | 1 / 20224 | 0.005% | 1 row (10s) |
| Combined OOD v1 | 281 / 20224 | 1.39% | 2 rows (20s) |
| High-noise (isolated) | 491 / 20224 | 2.43% | 2 rows (20s) |

The pilot's one rejection (a single-sample fuel_flow dip to 0.0747 SLPM,
surrounded by ~1.2-2.0 SLPM readings — a noise-driven outlier even at
*normal* noise levels, not a bug) confirms "zero or near-zero" is the
right framing for in-distribution data; the new, more physically
meaningful floors (vs. the original `1e-6` epsilon, which only caught
literal-zero clamping) catch more of these than before, by design.

**Frozen model/alert metrics**: row-level balanced accuracy is
unchanged for both OOD cohorts (insufficient-data rows were already
excluded from scoring before this PR, just via inferred nullability
rather than an explicit contract). False-alert rates shifted by a few
hundredths (combined: 12.34 → 12.06/healthy-hour; high-noise: 12.01 →
12.08/healthy-hour) — insufficient data now explicitly interrupts
pending confirmation and freezes exit/switch progress instead of the
state machine silently seeing a shorter, gapless row sequence.

**Closing the loop with PR172**: high-noise's rejection rate crossed
PR172's own 2% "materially important" threshold once computed under
the new, more sensitive floors (1.90% → 2.43%) — re-running
`shift_study` against the regenerated evaluations changes its
recommendation from PR172's **C** (broaden training coverage) to **A**
(numerically harden features first), which is exactly this PR's own
premise. This is a genuine, data-driven confirmation that the hardening
was warranted, not a circular argument — the threshold and the
recommendation logic were both fixed in PR172 before this PR existed.

---

## Limitations

- The two denominator floors are physically motivated, not fit to any
  dataset — they could still be wrong for a future fleet with a
  different rated curve; `docs` calls out the specific constants so a
  future PR can revisit them explicitly rather than silently.
- Only cross-signal ratios needed a policy change in this PR; if a future
  feature (e.g. a new ratio or a log/sqrt transform) is added, it must be
  routed through `features/safety.py`, not hand-rolled.
- This PR does not implement streaming/online inference — only designs
  `safety.py`'s functions to be reusable by a future one.

## Tests

`tests/backend/simulator/dataset/features/test_safety.py` (the policy
in isolation: every denominator sign/magnitude case, no NaN/Inf ever
returned), `test_rejection_contract.py` (hand-built minimal datasets
forcing exact rejections: one ratio invalid, both invalid, valid/
rejected disjointness, union-equals-eligible, near-floor boundary,
very-noisy-but-finite), `test_cross_signal.py` (updated for the new
`SafeDivisionResult` return type), `test_pilot_smoke.py` (regression:
pilot rejection rate stays near-zero). `tests/backend/simulator/dataset/
alert_policy/test_insufficient_data.py` (temporal policy: single and
consecutive insufficient-data rows, breaks pending, never clears
confirmed, never advances exit — including the "gap immediately after
partial exit progress still requires the full persistence count"
case that distinguishes *freeze* from *reset*). `tests/backend/simulator/
dataset/ood/` and `.../shift_study/` updated throughout for the renamed
`InsufficientDataSummary`/`insufficient_data` contract and the new
`availability` metrics block.

## Related documentation

- [Baseline Fault-Diagnosis Models](baseline-fault-diagnosis-models.md)
- [Uncalibrated Temporal Alert-State Policy](uncalibrated-temporal-alert-policy.md)
- [Out-of-Distribution Evaluation (OOD v1)](out-of-distribution-evaluation.md)
- [Isolated Distribution-Shift Study](isolated-shift-evaluation.md)
