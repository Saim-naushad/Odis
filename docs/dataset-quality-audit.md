# Dataset Quality Audit

This page describes the PR166 pilot-dataset quality-report capability —
generating and auditing the first real `pem-faults-pilot` dataset before
any feature engineering or model training begins. It assumes familiarity
with [Simulator Dataset Generation](simulator-dataset-generation.md).

Like dataset generation, this is a parallel, independent capability: it
does not touch `src/domain` or `src/application`, and nothing it produces
feeds the deterministic reasoning pipeline.

---

## Generating the pilot

```bash
pip install -e ".[dataset]"
python -m backend.simulator.dataset.generate \
  --spec examples/dataset_specs/pem_faults_pilot.json \
  --output datasets/pem-faults-pilot
```

`examples/dataset_specs/pem_faults_pilot.json` is the 64-run pilot spec:
16 runs per class (`normal_operation`, `cooling_degradation`,
`hydrogen_supply_issue`, `sensor_anomaly`), 4 runs per `(class,
target_asset)` stratum across all four Plant Alpha assets, 900 simulated
seconds per run at a 10-second sample interval, fault onset sampled from a
90–420s grid (10s steps) with a fixed 240s duration, severity sampled from
`[0.15, 1.0]`, sensor noise on all five core measurements, and a 60/20/20
run-level split.

**Why the generated dataset is not committed:** `datasets/` is
git-ignored (see `simulator-dataset-generation.md`) — Parquet output is
regenerable from the checked-in spec plus a pinned `simulator_version`, so
committing it would only bloat the repository with a large, derived
artifact that carries no information the spec doesn't already capture.
Only the spec JSON and this audit's own small test fixtures are checked in.

---

## Running the audit

```bash
pip install -e ".[dataset-analysis]"   # pyarrow + matplotlib, for plots
python -m backend.simulator.dataset.audit \
  --dataset datasets/pem-faults-pilot \
  --output datasets/pem-faults-pilot-audit
```

`--dataset-analysis` is optional: without it (just `.[dataset]`), the
audit still runs and writes `summary.json` + `quality_report.md`, but skips
the `plots/` directory and notes in the report that plotting was skipped.
`--no-plots` skips plotting explicitly even when matplotlib is installed.

The command exits **nonzero whenever any finding is `blocking`** — wire it
into CI or a pre-training gate the same way `pytest` is used today.

Output:

```
datasets/pem-faults-pilot-audit/
├── summary.json          # machine-readable: every finding + all computed statistics
├── quality_report.md     # human-readable report with the same content
└── plots/                # 7 focused PNGs (only with the dataset-analysis extra)
```

Both outputs are deterministic for a fixed, unchanged dataset directory —
neither embeds the audit run's own wall-clock time, only facts already
fixed by generation (the manifest's `created_at`, row counts, and findings
computed from the data itself).

---

## What the report checks

The audit (`backend/simulator/dataset/audit/`) loads the manifest, splits,
and all three Parquet tables, reconstructs the `DatasetSpec` that produced
them from the manifest's embedded `dataset_spec`, and runs six independent
check modules against that one in-memory snapshot:

| Module | Checks |
|---|---|
| `structural.py` | Schemas match `parquet_schema.py` exactly; manifest row counts and file hashes match the files on disk; re-planning the embedded spec (`run_plan.plan_runs` / `splits.assign_splits`) reproduces `runs.parquet` and `splits.json` exactly (class/asset/split counts included); every telemetry/ground-truth row references a known run; timestamps are monotonic per `(run, asset)`; sample cadence matches `dt_seconds`; units are stable per measurement; no unexpected nulls; no duplicate keys. |
| `labels.py` | Every `ground_truth.parquet` row is cross-checked against recomputing it from `runs.parquet` via `ground_truth.compute_ground_truth` (the same function generation itself calls) — plus raw invariants: only the target asset is ever faulty, inactive rows have zero severity, `seconds_since_fault_start` is null exactly when inactive, `sensor_anomaly` rows carry `sensor_corruption_type` (not `fault_type`) and vice versa for physical faults, healthy runs carry no active labels, and severity ramps monotonically. |
| `variation.py` | Run-level distributions for every load/initial-state/fault-timing field; flags identical same-class configurations, insufficient healthy-run spread, sampled values escaping the spec's declared ranges, or fault starts landing off the sampling grid. |
| `physical.py` | Compares each fault class's target-asset telemetry immediately before vs. during the fault, across all eight core+derived measurements, against the physically-expected signature for that class (see the module docstring for the exact physics reasoning). Each signature is `hard` (a reversal is `blocking`) or soft (a reversal is only `concerning`); an effect built from fewer than 5 runs is never allowed to reach `blocking`, since that little evidence can't distinguish a real effect from a coincidental one. |
| `separability.py` | A direct (no scikit-learn, no persisted model) single-threshold sweep per `(class, measurement)`, load-band-controlled, flagging any pair separable by a raw value alone — informational, since high separability is *good* for a measurement the class is expected to move, and *leakage* for one it isn't. |
| `leakage.py` | Explicitly tests 11 candidate leakage sources (run ID, dataset ID, target asset, split, duration, row count, timestamps, missingness, noise config, measurement availability, fault-start policy) and produces the future feature-exclusion list — the `runs.parquet` columns (`simulation_run_id`, `fault_start_sim_seconds`, etc.) that encode the label by construction and must never be fed to a model. |

`plots.py` renders exactly the seven plots the design calls for (onset-
aligned trajectories, healthy-vs-fault distributions, voltage/current
relationship, severity-vs-effect, fault-start/severity coverage, split
balance, sensor-noise residuals) — no decorative dashboard.

---

## Interpreting the verdict

`verdict.py` derives one of three verdicts from the single worst finding
severity present — never forced positive:

- **READY FOR FEATURE ENGINEERING** — no `blocking` or `high` finding.
- **READY WITH DATASET POLICY CHANGES** — no `blocking` finding, but at
  least one `high` finding (e.g. a class concentrated on one target asset)
  that a future spec change could fix.
- **NOT READY — SIMULATOR OR LABEL CORRECTIONS REQUIRED** — at least one
  `blocking` finding: a structural-contract violation, a label that
  doesn't match its own run configuration, or a fault class whose *hard*
  physical signature is reversed with enough runs to be confident about it.

`low`/`medium` findings (e.g. the always-present "run ID embeds the class"
leakage note) are informational and never affect the verdict or exit code.

---

## Tests

`tests/backend/simulator/dataset/audit/` generates one small, real
(physics-produced, not hand-built) 8-run dataset per test via the existing
`spec_factory` fixture, then either audits it directly (valid-dataset,
determinism, CLI, plot-generation cases) or mutates a copy of one file to
inject a single deliberate defect (split overlap, an unknown run
reference, a cadence violation, a unit inconsistency, a label/window
mismatch, a non-target-asset false label) and asserts the corresponding
`Finding` appears. Nothing here runs against the full 64-run pilot — that
would be slow and isn't necessary to prove the check logic itself is
correct.

---

## Related documentation

- [Simulator Dataset Generation](simulator-dataset-generation.md)
- `backend/simulator/dataset/audit/physical.py` — the physics reasoning
  behind each fault class's expected telemetry signature
- `backend/simulator/dataset/audit/leakage.py` — the future
  feature-exclusion list and why each excluded column encodes the label
