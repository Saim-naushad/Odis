# Simulator Dataset Generation

This page describes how to generate and inspect versioned, offline
Parquet datasets from the Plant Alpha simulator — the PR161-164 slice of
the ODIS v1.1 ML data extension. It assumes familiarity with
[the simulator](simulator.md).

For the reasoning-engine architecture, this is a parallel, independent
capability: it does not touch `src/domain` or `src/application`, and
nothing generated here feeds the deterministic reasoning pipeline.

---

## What this produces

A directory of the form:

```
datasets/<dataset_id>/
├── telemetry.parquet        # one row per emitted observation
├── ground_truth.parquet     # one row per asset per sample time
├── runs.parquet             # one row per planned run
├── splits.json              # disjoint train/validation/test run IDs
├── dataset_manifest.json    # reproducibility metadata, file hashes
└── data_dictionary.md       # field-by-field documentation
```

See `data_dictionary.md` inside any generated dataset for exact table
schemas, units, and null semantics — it is copied verbatim from
`backend/simulator/dataset/templates/data_dictionary.md` and always
matches the schemas in `backend/simulator/dataset/parquet_schema.py`.

**Supported classes in this dataset version:** `normal_operation`,
`cooling_degradation`, `hydrogen_supply_issue`, `sensor_anomaly` (bias
ramp only). Membrane dehydration, combined faults, and other sensor
corruption modes are not supported — do not assume a generated dataset
contains them.

---

## Installing

Parquet generation needs `pyarrow`, which is **not** part of the base
install (API, worker, live simulator, and demo installs are unaffected):

```bash
pip install -e ".[dataset]"
```

(`pip install -e ".[dev]"` also includes it, for running the test suite.)

---

## Generating a dataset

```bash
python -m backend.simulator.dataset.generate \
  --spec examples/dataset_specs/pem_faults_tiny.json \
  --output datasets/pem-faults-tiny
```

- `--spec` points at a JSON `DatasetSpec` (see below). `examples/dataset_specs/pem_faults_tiny.json` is a small, fixed-value smoke-test example covering all four supported classes. `examples/dataset_specs/pem_faults_pilot.json` is the quality-audit pilot spec (64 runs, 16 per class, ranged fault start/severity per PR165) — not yet generated or committed as a dataset.
- `--output` overrides the spec's own `output_directory` field.
- `--overwrite` is required to replace an existing non-empty output directory; without it, generation refuses to run rather than silently merging into old data.

The CLI prints one line per completed run (not per sample) and, on
success, the final path and row/split counts. It exits non-zero on any
failure and never leaves a directory that looks complete at the requested
output path — see [Output lifecycle](#output-lifecycle-and-failure-handling)
below.

Generated dataset directories are **not** committed — `datasets/` is
git-ignored. Only the small spec files under `examples/dataset_specs/`
are checked in.

---

## Writing a dataset specification

A `DatasetSpec` (`backend/simulator/dataset/dataset_spec.py`) is policy,
not already-resolved runs:

| Field | Meaning |
|---|---|
| `dataset_id` | Used to derive every run ID and the split-shuffle RNG seed. |
| `scenario_plans` | A list of `{scenario_name, run_count, ...}` — one entry per class you want in the dataset. Each fault plan sets `fault_duration_sim_seconds` plus **either** a fixed `fault_start_sim_seconds`/`fault_severity` **or** a per-run-sampled `fault_start_range`/`fault_severity_range` (PR165) — never both. A ranged plan draws one value per run from a seed-derived RNG stream isolated from operating-condition and sensor-noise sampling, so runs of the same class no longer share an identical fault onset and magnitude. `fault_start_range` is a discrete grid (`{minimum_seconds, maximum_seconds, step_seconds}`); `fault_severity_range` is continuous (`{minimum, maximum}`). A `scenario_name` must not repeat across plans — see `examples/dataset_specs/pem_faults_pilot.json` for a worked example. |
| `seeds` | Flat list, exactly as long as the total run count across all `scenario_plans`; consumed sequentially in `scenario_plans` order. |
| `target_asset_ids` | Round-robins per scenario plan, for target-asset balance within each class. |
| `duration_sim_seconds` / `dt_seconds` | Uniform across every run in this dataset version. |
| `run_start_time` | The fixed anchor every run's telemetry timestamps are computed from — never wall-clock. |
| `operating_condition_ranges` | Sampling ranges for the seeded load-profile/initial-state variation (PR163). |
| `sensor_noise` | Fixed (not seed-sampled) per-measurement Gaussian noise config, applied identically across every run. |
| `split_proportions` | Target train/validation/test fractions, applied per `(class, target_asset)` stratum. |
| `output_directory` | Default output path; overridable by `--output`. |

**Reproducibility contract:** the same `DatasetSpec` always resolves to
the same run plan (run IDs, seeds, target assets), the same resolved
operating conditions per run, and therefore the same telemetry and ground
truth. See `dataset_manifest.json`'s `reproducibility` section for the
precise (semantic vs. byte-level) guarantee.

---

## Output lifecycle and failure handling

`generate_dataset` writes everything to a fresh temporary directory next
to the requested output path, and only atomically renames it into place
once every file — including `dataset_manifest.json`, written last — has
been produced successfully. If any run fails, the temporary directory is
removed, the error names the failed run, and the requested output path is
left exactly as it was before the attempt (untouched, or still the prior
successful dataset). Re-running is always safe.

---

## Inspecting a generated dataset

```python
import pyarrow.parquet as pq

telemetry = pq.read_table("datasets/pem-faults-tiny/telemetry.parquet")
ground_truth = pq.read_table("datasets/pem-faults-tiny/ground_truth.parquet")
runs = pq.read_table("datasets/pem-faults-tiny/runs.parquet")
```

or, from the shell, with any Parquet-aware tool (`parquet-tools`, DuckDB,
etc. — none of these are project dependencies, just compatible readers).

---

## Related documentation

- [Fuel cell simulator](simulator.md)
- `backend/simulator/dataset/telemetry.py` — why noisy core and derived telemetry never mix with clean hidden state (the PR163 raw/derived consistency correction)
- `backend/simulator/dataset/templates/data_dictionary.md` — the field-level contract copied into every generated dataset
