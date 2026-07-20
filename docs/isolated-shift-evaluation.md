# Isolated Distribution-Shift Study (PR172)

This page describes PR172 — a controlled follow-up to
[Out-of-Distribution Evaluation (OOD v1)](out-of-distribution-evaluation.md).
PR171's combined OOD v1 dataset shifted load, initial temperature, fault
onset, and sensor noise simultaneously, so it could report *that*
generalization failed but not, with confidence, *which* shift caused it.
PR172 evaluates the same frozen PR168 model and PR170 alert policy
against four datasets that each change exactly **one** dimension, so the
source of failure can be identified before any feature or model work
begins.

Like PR171, this is evaluation-only: no retraining, recalibration,
threshold tuning, feature change, or simulator change happens here.

---

## Why isolated-shift evaluation is necessary

A single combined-shift dataset can tell you generalization degrades; it
cannot reliably tell you *why*, because every candidate feature that
moved could plausibly explain the result. PR171 was explicit about this
gap — its feature-shift ranking pointed at load, but it correctly refused
to claim causal isolation. PR172 closes that gap the direct way: hold
three dimensions fixed at the pilot's own values and change only the
fourth, one dataset at a time.

## The four cohorts

Each isolated dataset mirrors the pilot exactly (64 runs, 16/class, same
4 assets, 10s cadence, 900s duration, persistent-fault policy, disjoint
seeds) except for one field group:

| Cohort | Spec | Changed | Held at pilot's value |
|---|---|---|---|
| `high_load` | `pem_faults_shift_high_load.json` | baseline load 68-82%, amplitude narrowed to 5-10% (see below) | initial temp, fault onset, noise |
| `hot_start` | `pem_faults_shift_hot_start.json` | initial stack-temp offset +4 to +8°C | load, fault onset, noise |
| `late_onset` | `pem_faults_shift_late_onset.json` | fault onset 500-600s (240s ramp, 10s grid) | load, initial temp, noise |
| `high_noise` | `pem_faults_shift_high_noise.json` | 5 core-channel noise stdevs ~doubled, same 3σ clip | load, initial temp, fault onset |

**Why `high_load`'s amplitude is narrowed** (5-18% → 5-10%): identical to
PR171's own reasoning — `OperatingConditions` enforces `baseline ±
amplitude ∈ [5, 95]`, and the pilot's amplitude range at the new 68-82%
baseline can reach 100%. Narrowing is the smallest change that makes the
requested load shift generatable at all; every other cohort keeps the
pilot's operating-condition fields unchanged.

Seeds: pilot uses 1001-4016, OOD v1 uses 11001-14016, and the four
isolated cohorts use 21001-24016 (`high_load`), 31001-34016
(`hot_start`), 41001-44016 (`late_onset`), 51001-54016 (`high_noise`) —
verified pairwise disjoint across all six datasets by
`test_shift_specs.py`.

## What remains frozen

Exactly PR171's own frozen set: the PR168 `selected_pipeline.joblib`
(logistic regression, feature set D, `C=0.01`), the PR167 153-feature
contract, and the PR170 alert-policy state machine. PR172 adds nothing
new to freeze — it *reuses* PR171's `ood.artifacts.load_frozen_artifacts`
compatibility checks and its `ood.data_loading`/`ood.diagnosis_metrics`/
`ood.alert_metrics` computation, never reimplementing them.

## Study architecture: consume, don't recompute

`backend/simulator/dataset/shift_study/` does not fit a model, compute a
confusion matrix, or run the alert state machine itself. Every number it
reports is read from an already-produced PR171 `ood_evaluation_summary.
json`/`feature_shift.json`/`error_cases.json` — one per cohort, each
produced by running the existing `python -m backend.simulator.dataset.
ood` CLI with that cohort's features as the "OOD" side and the pilot's
own features/model/alert-policy as the frozen reference. `shift_study`
only aggregates, ranks, classifies, and narrates.

---

## Running the study

```bash
pip install -e ".[ml]"

# For each of high-load, hot-start, late-onset, high-noise:
python -m backend.simulator.dataset.generate \
  --spec examples/dataset_specs/pem_faults_shift_high_load.json \
  --output datasets/pem-faults-shift-high-load
python -m backend.simulator.dataset.audit \
  --dataset datasets/pem-faults-shift-high-load \
  --output datasets/pem-faults-shift-high-load-audit
python -m backend.simulator.dataset.features \
  --dataset datasets/pem-faults-shift-high-load \
  --output datasets/pem-faults-shift-high-load-features
python -m backend.simulator.dataset.ood \
  --training-features datasets/pem-faults-pilot-features \
  --ood-features datasets/pem-faults-shift-high-load-features \
  --models datasets/pem-faults-pilot-models \
  --alert-policy datasets/pem-faults-pilot-alert-policy \
  --output datasets/pem-faults-shift-high-load-evaluation

# Then combine every cohort into one study:
python -m backend.simulator.dataset.shift_study \
  --combined-ood-evaluation datasets/pem-faults-ood-v1-evaluation \
  --cohort high_load=datasets/pem-faults-shift-high-load-evaluation \
  --cohort hot_start=datasets/pem-faults-shift-hot-start-evaluation \
  --cohort late_onset=datasets/pem-faults-shift-late-onset-evaluation \
  --cohort high_noise=datasets/pem-faults-shift-high-noise-evaluation \
  --audit high_load=datasets/pem-faults-shift-high-load-audit \
  --audit hot_start=datasets/pem-faults-shift-hot-start-audit \
  --audit late_onset=datasets/pem-faults-shift-late-onset-audit \
  --audit high_noise=datasets/pem-faults-shift-high-noise-audit \
  --output datasets/pem-faults-shift-study
```

`--audit NAME=PATH` is optional per cohort (only the "Physical audit"
report section is affected by omitting it). There is no `--id-evaluation`
flag: every PR171 evaluation output already embeds the identical pilot
test-split metrics it was itself scored against, so nothing further is
needed — see `shift_study/cohort_loading.CohortData.id_diagnosis` and the
artifact-fingerprint consistency check `load_cohorts` runs across every
supplied cohort.

Output:

```
datasets/pem-faults-shift-study/
├── shift_study_summary.json     # fingerprint, rankings, interaction analysis, verdict
├── shift_study_report.md        # human-readable report
├── cohort_metrics.json          # full per-cohort diagnosis/alerts/feature-shift/audit/cases
├── cohort_rankings.json         # per-shift damage + per-metric rankings
├── invalid_feature_rows.json    # unscoreable-row rollup across cohorts
└── plots/
    ├── metric_degradation_by_shift.png
    ├── false_alerts_by_shift.png
    ├── per_class_recall_by_shift.png
    ├── feature_shift_by_cohort.png
    └── representative_shift_timelines.png
```

---

## Severity classification

Four tiers — `minor` / `moderate` / `major` / `catastrophic` — fixed in
`shift_study/config.py` **before** any isolated cohort was evaluated.
`catastrophic` reuses PR171's own "does not generalize" bar exactly (a
class recall collapse, an excessive missed-run fraction, a false-alert
rate above 5/healthy-hour, or balanced accuracy at/below 0.40); `major`
is triggered by exceeding PR171's "acceptable" bar (balanced-accuracy
drop > 0.15, false-alert rate > 1.0/healthy-hour, or missed-run fraction
> 0.25) on any one metric; `minor` requires a drop ≤ 0.05 **and** no
meaningful alert-rate or missed-run increase; everything else is
`moderate`. See `config.SHIFT_CLASSIFICATION_DESCRIPTION` for the exact
rule as applied.

## Results

|  | ID (pilot test) | high_load | hot_start | late_onset | high_noise | combined (PR171) |
|---|---|---|---|---|---|---|
| Balanced accuracy | 0.855 | 0.819 | 0.852 | 0.796 | 0.708 | 0.580 |
| Tier | — | major | moderate | moderate | **catastrophic** | catastrophic |
| False alerts/healthy-hour | — | 1.10 | 0.94 | 0.44 | 12.01 | 12.34 |
| Any-fault missed runs | — | 0 | 0 | 0 | 4 | 3 |
| Unscoreable rows | — | 0.00% | 0.00% | 0.00% | **1.90%** | 1.02% |

**High sensor noise, not high load, is the dominant isolated failure
mode** — a correction to PR171's own tentative, appropriately-hedged
inference that load looked most implicated by the feature-shift ranking.
In isolation, `high_load` only reaches `major` (driven by its false-alert
rate crossing 1.0/hour, not by balanced accuracy, which barely drops).
`high_noise` alone reproduces almost the entire combined-cohort
false-alert catastrophe (12.01 vs. 12.34/healthy-hour) and is the only
isolated shift to collapse healthy-row precision.

**Combined vs. isolated**: the combined balanced-accuracy drop (0.275)
meets or slightly exceeds the naive additive sum of the four isolated
drops (0.244) — labeled `INTERACTION EFFECTS LIKELY: yes`, though this is
an inference from an unpaired design, not a measured factorial effect
(see limitations).

**Late onset**: post-ramp recall (~0.98) is far higher than ramp-stage
recall (~0.64) in the `late_onset` cohort — its degradation reads mainly
as a shorter evaluable post-ramp window in a fixed 900s run, not a
distinct diagnosis failure once a fault fully develops.

**Hot start and cooling degradation**: in `hot_start`, healthy rows are
misclassified as `cooling_degradation` more than any other fault class
(662 rows), and `cooling_degradation` has the lowest precision among
fault classes (0.53) — consistent with a hot initial state resembling
cooling degradation's thermal signature, though still only a `moderate`
shift overall.

**Invalid rows**: the zero-denominator `power_per_fuel_flow` null found
in PR171 occurs almost exclusively under `high_noise` (1.90%, 385/20224
rows) and negligibly elsewhere (`hot_start`: 1 row; `high_load`/
`late_onset`: 0). It did **not** trigger recommendation A here — 1.90% is
below the 2% materiality threshold, and the cohort's dominant problem
(healthy-row misclassification, not missing features) is clearly
numerical-sensitivity-driven rather than missing-data-driven.

## Study verdict

- **PRIMARY GENERALIZATION FAILURE**: `high_noise`
- **SECONDARY FAILURE**: `high_load`
- **MINOR CONTRIBUTORS**: `late_onset`, `hot_start`
- **INTERACTION EFFECTS LIKELY**: yes (inference, not measured)
- **Recommended next direction: C** — broaden training-distribution
  coverage first. Neither A (invalid-row fraction stays under the
  materiality threshold everywhere) nor B (`high_load` is not the sole
  major/catastrophic shift — `high_noise` is worse) nor D (only 2/4
  isolated shifts reach major-or-worse, not the 3+ needed) matched; see
  `verdict.determine_recommendation` for the exact decision tree.

---

## Limitations

- **Unpaired, not factorial seeds**: each cohort uses independent seeds
  from the others. No dataset varies two shifts together in a controlled
  way, so the interaction-effects finding above is inference from
  comparing aggregate drops, never a measured causal interaction. A
  future PR could add paired/factorial cohorts if isolating interactions
  becomes a priority.
- Only 16 runs per fault class per cohort — severity tiers and rankings
  are indicative at this scale, not statistically robust.
- Simulator-only evidence from Plant Alpha's first-order-lag physics
  model.

## Tests

`tests/backend/simulator/dataset/shift_study/` covers: the four
committed specs (load, plan 64 runs, class/asset balance, seed
disjointness against pilot/OOD-v1/each other, fault-window fit, and that
each spec changes only its intended dimension); cohort loading (missing
file, duplicate name, artifact-hash-mismatch rejection); tier
classification and per-metric ranking (every boundary, determinism);
invalid-row aggregation (per-cohort rollup, zero-invalid case,
determinism); the study verdict (primary/secondary/tie-break selection,
all four A/B/C/D recommendation branches); the interaction heuristic
(explained-by-worst-shift / uncertain / likely bands, graceful handling
of a missing cohort); and an end-to-end smoke test against tiny synthetic
evaluation-summary fixtures (never full dataset regeneration, per the
spec's own guidance) checking every output artifact, reproducibility, and
recorded artifact hashes.

## Related documentation

- [Baseline Fault-Diagnosis Models](baseline-fault-diagnosis-models.md)
- [Calibrated Confidence, Abstention, and Alert Policy](calibrated-confidence-and-alert-policy.md)
- [Uncalibrated Temporal Alert-State Policy](uncalibrated-temporal-alert-policy.md)
- [Out-of-Distribution Evaluation (OOD v1)](out-of-distribution-evaluation.md)
