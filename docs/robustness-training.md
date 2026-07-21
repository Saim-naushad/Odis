# Broader-Regime Training and Robustness Evaluation (PR174)

This page describes PR174 — the first robustness-training iteration
following [Isolated Distribution-Shift Study (PR172)](isolated-shift-evaluation.md),
which found **high sensor noise** to be the primary isolated
generalization failure (secondary: high load; minor: late onset, hot
start) and [PR173's numerical-safety and insufficient-data
contract](numerically-safe-features.md). The question this PR answers is
narrow and controlled:

> Does intentionally broadening the training distribution across
> realistic noise and load regimes improve performance on unseen shifted
> cohorts while preserving original-regime performance?

It is **not** "can pooling every available dataset produce the highest
score" — the robust training dataset is deliberately disjoint from every
evaluation cohort (including the pilot, which is used only as an external
ID check), uses new seeds, and is trained/selected with the same fixed
model families, feature ablations, and hyperparameter grids PR168 already
committed to. No new classifier family, feature definition, calibration,
alert-policy tuning, or simulator change happens here.

---

## Why broader coverage was added

PR172's isolated evaluation showed the frozen PR168 model's diagnosis and
alert-policy performance degrades sharply once sensor noise (and, to a
lesser extent, load) moves outside the pilot's narrow training envelope.
The model was never shown that regime during training — broadening the
*training* distribution, not just re-scoring against wider *evaluation*
cohorts, is the direct way to test whether the failure is a data-coverage
problem (fixable by broader training) or an architectural one (not
fixable by more data alone).

## How the robust training distribution differs from evaluation cohorts

The robust training spec
(`examples/dataset_specs/pem_faults_robust_training_v1.json`) covers a
middle ground between the pilot and each isolated shift cohort — it does
not copy any evaluation cohort's exact range as a block:

| Dimension | Pilot | Robust training | High-noise/high-load eval cohorts |
|---|---|---|---|
| Load baseline | 50-70% | **45-80%** | 68-82% (high-load only) |
| Load amplitude | 5-18% | **5-15%** (kept valid across the wider baseline range — see below) | 5-10% |
| Initial temp offset | -3 to +3°C | **-4 to +7°C** | +4 to +8°C (hot-start only) |
| Fault onset | 90-420s | **90-600s** | 500-600s (late-onset only) |
| Sensor noise | one fixed profile | **sampled per run from 3 named regimes** (nominal/moderate/high_bounded) | one fixed doubled profile |

The load-amplitude range was narrowed from the pilot's 5-18% to 5-15%
specifically so that `load_baseline_percent + load_amplitude_percent`
never exceeds the simulator's documented `[5, 95]` operating-envelope
constraint anywhere in the broadened 45-80% baseline range (at the
baseline's upper end, 80 + 15 = 95 exactly; the existing 18%-wide pilot
amplitude would have overshot to 98 there).

### Noise-regime sampling: a small, isolated schema extension

Before this PR, `DatasetSpec.sensor_noise` was a single fixed,
dataset-wide noise configuration — every run in a dataset got the
identical noise scale. To let each run in the robust training set draw
from one of several noise regimes (rather than hand-authoring three
duplicate scenario plans), `operating_conditions.py` gained:

- `NoiseRegime` — a named, fixed `sensor_noise` tuple (mirrors
  `SensorNoiseConfig`'s existing shape at the profile level).
- `resolve_sensor_noise(fixed, regimes, rng)` — mirrors
  `fault_variation.resolve_fault_start`/`resolve_fault_severity`'s
  fixed-or-ranged pattern exactly: `regimes` takes precedence when
  non-empty; returns `fixed` unchanged, touching `rng` not at all,
  otherwise.
- `DatasetSpec.sensor_noise_regimes: tuple[NoiseRegime, ...]` — mutually
  exclusive with `sensor_noise` (validated in `__post_init__`), requires
  at least 2 uniquely-named regimes when set.
- A **new, fully isolated RNG stream** — `f"{seed}:sensor_noise_regime"`
  — built in `run_template.resolve_run_config`, alongside (never mixed
  with) the existing `operating_conditions`, `fault_variation`, and
  per-sample `sensor_noise` streams. Isolating it means the noise-regime
  draw changes nothing about a run's sampled load/initial-state/fault
  timing for the same seed — verified directly in
  `test_run_template.py`.

Noise is still **applied** exactly as before (`sensor_noise.
apply_sensor_noise`, unchanged) — only *which* fixed profile a run
receives is now resolvable per-seed. Existing specs (pilot, all four
PR172 isolated cohorts, OOD v1) are unaffected: they never set
`sensor_noise_regimes`, so they resolve identically to before this PR.

The robust training spec defines three regimes — `nominal` (matches the
pilot's stdevs exactly), `moderate` (the arithmetic midpoint), and
`high_bounded` (matches the high-noise-only cohort's doubled stdevs). Each
of the 192 runs draws one regime independently; the realized split was
66 `high_bounded` / 64 `nominal` / 62 `moderate` — roughly even, not
dominated by any one regime.

## Why external cohorts remain untouched

The pilot's own test split and all five PR171/172 evaluation cohorts
(`high_load`, `hot_start`, `late_onset`, `high_noise`, `combined_ood_v1`)
keep their original seeds, ranges, and generated artifacts — none of them
were regenerated or touched by this PR. The robust training spec's seed
block (`61001`-`64048`) is disjoint from every other committed spec's
seeds (verified in `test_robust_training_spec.py`), and the pilot is used
only as a *held-out* external evaluation cohort (its own test split),
never merged into the robust training set. This is what makes the
promotion comparison meaningful: every number reported for the robust
candidate on an external cohort reflects genuine generalization, not
data the model (directly or indirectly) trained on.

## Promotion criteria

Defined in `backend/simulator/dataset/robustness/config.py` (`
PromotionThresholds`) before any evaluation result was read:

- Pilot balanced-accuracy drop <= 0.03
- Pilot false-alert rate <= 1.0 events/healthy-hour
- High-noise balanced-accuracy gain >= 0.02 (material improvement)
- High-noise false-alert rate <= 1.0 events/healthy-hour
- Combined-OOD balanced-accuracy gain >= 0.02
- No fault class's recall drops to <= 0.20 on any cohort (class collapse)
- No cohort's correct-class missed-run count increases by more than 1

Any class collapse forces `NO MODEL READY`; a pilot regression (accuracy
or false alerts) forces `KEEP ORIGINAL — ID REGRESSION TOO LARGE`;
missing the gain/false-alert bars with no regression forces `KEEP
ORIGINAL — ROBUSTNESS GAINS INSUFFICIENT`; only meeting every bound
promotes.

## Results (summary — see `robust_evaluation_report.md` for full detail)

Trained on the 192-run robust dataset, the same PR168 ablation search
selected **logistic regression / feature group D**, same family as
PR168's own selection, with `C=10.0` (vs. PR168's `C=0.01` — a materially
less-regularized fit, consistent with more training data supporting a
less-constrained model).

| Cohort | Original BA | Robust BA | Change |
|---|---|---|---|
| pilot (external, test split) | 0.855 | 0.885 | **+0.031** |
| high_load | 0.819 | 0.871 | +0.052 |
| hot_start | 0.852 | 0.878 | +0.026 |
| late_onset | 0.796 | 0.809 | +0.013 |
| **high_noise** | 0.709 | 0.855 | **+0.146** |
| **combined_ood_v1** | 0.580 | 0.743 | **+0.163** |

Every cohort improved, most dramatically the two PR172 flagged the
worst. False-alert rate on `high_noise` fell from 12.08 to 1.40
events/healthy-hour and `correct_class_missed_run_count` fell from 6 to
0; on `combined_ood_v1` it fell from 12.06 to 0.99. No fault class
collapsed on any cohort.

**Decision: `KEEP ORIGINAL MODEL — ROBUSTNESS GAINS INSUFFICIENT`.** Every
criterion passed except one: `high_noise`'s false-alert rate (1.40)
remains above the 1.0 operational bound, even though it improved by 8.6x.
This is not a broken policy — it works and even improves on 4 of 6
cohorts unchanged — but it does not clear this PR's own pre-committed
bar on the cohort that matters most. See "Limitations" below for the
follow-up this implies.

## Limitations

- The frozen PR170 alert policy (entry=0.60/persistence=4,
  exit=0.50/persistence=2) was evaluated unchanged, per this PR's scope.
  Its false-alert rate under the robust model's different probability
  calibration is the single reason promotion criteria were not fully met
  — a dedicated policy-retuning PR (re-searching the same PR170 grid
  against the robust model's validation split) is a reasonable next step,
  not undertaken here.
- Per-class recall is not uniformly better: on the noisiest cohorts, the
  robust model trades a little fault-vs-fault discrimination (e.g.
  `cooling_degradation`/`hydrogen_supply_issue` recall dips slightly on
  `combined_ood_v1`) for much better healthy-vs-fault separation. None of
  these dips approach the 0.20 collapse floor.
- Synthetic-data caveat: every number above comes from Plant Alpha's
  first-order-lag physics simulator, not physical hardware — the relative
  comparison (broader training helps under simulated noise) is the
  evidence; the absolute accuracy figures are not a hardware claim.
- 192 runs (12/stratum) is materially more than the 64-run pilot but
  still small per noise-regime/class cell; per-regime performance
  breakdowns in `robust_training_summary.json` should be read as
  indicative, not statistically definitive.

## Artifacts

```
datasets/pem-faults-robust-training-v1/                  # generated dataset (192 runs)
datasets/pem-faults-robust-training-v1-audit/            # quality audit (READY, 0 blocking/high)
datasets/pem-faults-robust-training-v1-features/         # 153-column features + feature_rejections.parquet
datasets/pem-faults-robust-training-v1-models/           # robust candidate's own models-CLI output
datasets/pem-faults-robust-training-v1-comparison/
    robust_candidate_pipeline.joblib     # copy of the selected robust pipeline (PR168's own artifact untouched)
    robust_candidate_metadata.json
    robust_training_summary.json         # manifest/feature hashes, class/feature order, cohort hashes
    robust_evaluation_report.md          # full per-cohort diagnosis/alert comparison
    promotion_decision.json              # decision, reasons, thresholds, checks
    cohort_comparisons.json
```

## Tests

`tests/backend/simulator/dataset/test_robust_training_spec.py` covers the
committed spec: loads and plans 192 runs; class/asset/stratum balance;
seed disjointness against every other committed spec; fault-window fit;
load/temperature/onset broadened-but-not-copied coverage; noise-regime
declaration and per-run resolution/coverage.

`test_operating_conditions.py`/`test_run_template.py`/`test_dataset_spec.py`
cover the schema extension itself: `NoiseRegime` validation and JSON
round-trip; `resolve_sensor_noise`'s fixed-vs-regime behavior and RNG
determinism; the new isolated RNG stream never shifting operating-
condition or fault-variation draws for the same seed; `DatasetSpec`'s
mutual-exclusivity and minimum-regime-count validation.

`tests/backend/simulator/dataset/robustness/` covers the new comparison
package: artifact loading and its compatibility checks (missing file,
unknown feature group, column mismatch, schema-version mismatch);
`compare_models_on_cohort`'s delta computation for every metric;
`decide_promotion`'s four outcomes (promote, insufficient gain, ID
regression from either accuracy or false alerts, class collapse) plus a
missed-run-regression case and deterministic near-threshold behavior; and
an end-to-end smoke test against small, real (physics-generated)
fixtures — never the full 192-run dataset — verifying every output
artifact is written, the copied candidate pipeline predicts identically
to the original, and every cohort is scored through the same frozen
artifact.

## Related documentation

- [Baseline Fault-Diagnosis Models](baseline-fault-diagnosis-models.md)
- [Numerically-Safe Features and Insufficient-Data Handling](numerically-safe-features.md)
- [Uncalibrated Temporal Alert-State Policy](uncalibrated-temporal-alert-policy.md)
- [Out-of-Distribution Evaluation (OOD v1)](out-of-distribution-evaluation.md)
- [Isolated Distribution-Shift Study](isolated-shift-evaluation.md)
