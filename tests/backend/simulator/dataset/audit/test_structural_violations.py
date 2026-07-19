"""Structural-contract violation detection (PR166 spec sections 3 and 11).

Each test injects exactly one deliberate defect into a copy of a valid
generated dataset's files, then asserts `check_structural` reports it.
Mutating a data file after generation also invalidates that file's
manifest hash/row-count entries, which independently produces its own
"blocking" finding — tests assert the *targeted* finding is present among
others, not that it is the only one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

from backend.simulator.dataset.audit.findings import Finding
from backend.simulator.dataset.audit.loader import load_dataset
from backend.simulator.dataset.audit.records import build_records
from backend.simulator.dataset.audit.structural import check_structural
from backend.simulator.dataset.parquet_schema import (
    GROUND_TRUTH_SCHEMA,
    TELEMETRY_SCHEMA,
)

from .conftest import read_rows, write_rows


def _findings_mentioning(findings: list[Finding], *phrases: str) -> list[Finding]:
    return [f for f in findings if any(phrase in f.message for phrase in phrases)]


def test_split_overlap_is_detected(tiny_dataset_dir: Path) -> None:
    splits_path = tiny_dataset_dir / "splits.json"
    splits = json.loads(splits_path.read_text())
    assert splits["train"], "fixture must have at least one train run"
    duplicated_run_id = splits["train"][0]
    splits["validation"] = [*splits["validation"], duplicated_run_id]
    splits_path.write_text(json.dumps(splits, indent=2))

    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)
    findings = check_structural(handle, records)

    matches = _findings_mentioning(
        findings, "assigned to both the train/validation splits"
    )
    assert matches
    assert matches[0].severity == "blocking"


def test_unknown_run_reference_in_telemetry_is_detected(tiny_dataset_dir: Path) -> None:
    telemetry_path = tiny_dataset_dir / "telemetry.parquet"
    rows = read_rows(telemetry_path)
    bogus_row = dict(rows[0])
    bogus_row["simulation_run_id"] = "does-not-exist-in-runs-parquet"
    bogus_row["observation_id"] = "bogus-observation"
    rows.append(bogus_row)
    write_rows(telemetry_path, rows, TELEMETRY_SCHEMA)

    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)
    findings = check_structural(handle, records)

    matches = _findings_mentioning(
        findings, "telemetry.parquet has 1 row(s) referencing run IDs not present"
    )
    assert matches
    assert matches[0].severity == "blocking"


def test_cadence_violation_is_detected(tiny_dataset_dir: Path) -> None:
    ground_truth_path = tiny_dataset_dir / "ground_truth.parquet"
    rows = read_rows(ground_truth_path)
    first_run_id = rows[0]["simulation_run_id"]
    first_asset_id = rows[0]["asset_id"]
    for row in rows:
        if (
            row["simulation_run_id"] == first_run_id
            and row["asset_id"] == first_asset_id
            and row["elapsed_sim_seconds"] == 60.0
        ):
            row["elapsed_sim_seconds"] = 65.0  # off the 30s dt_seconds cadence
            break
    write_rows(ground_truth_path, rows, GROUND_TRUTH_SCHEMA)

    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)
    findings = check_structural(handle, records)

    matches = _findings_mentioning(findings, "sample interval that is not consistently")
    assert matches
    assert matches[0].severity == "blocking"


def test_unit_inconsistency_is_detected(tiny_dataset_dir: Path) -> None:
    telemetry_path = tiny_dataset_dir / "telemetry.parquet"
    rows = read_rows(telemetry_path)
    for row in rows:
        if row["measurement_type"] == "voltage":
            row["unit"] = "mV"  # every other voltage row stays "V"
            break
    write_rows(telemetry_path, rows, TELEMETRY_SCHEMA)

    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)
    findings = check_structural(handle, records)

    matches = _findings_mentioning(
        findings, "reports more than one unit for the same measurement_type"
    )
    assert matches
    assert matches[0].severity == "blocking"


def test_duplicate_ground_truth_key_is_detected(tiny_dataset_dir: Path) -> None:
    ground_truth_path = tiny_dataset_dir / "ground_truth.parquet"
    rows = read_rows(ground_truth_path)
    rows.append(dict(rows[0]))  # exact duplicate of an existing row
    write_rows(ground_truth_path, rows, GROUND_TRUTH_SCHEMA)

    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)
    findings = check_structural(handle, records)

    matches = _findings_mentioning(findings, "duplicate row(s) for key")
    assert matches
    assert matches[0].severity == "blocking"


def test_structural_violation_causes_nonzero_audit_exit(
    tmp_path: Path, tiny_dataset_dir: Path
) -> None:
    from backend.simulator.dataset.audit.report import run_audit

    splits_path = tiny_dataset_dir / "splits.json"
    splits = json.loads(splits_path.read_text())
    splits["validation"] = [*splits["validation"], splits["train"][0]]
    splits_path.write_text(json.dumps(splits, indent=2))

    result = run_audit(
        tiny_dataset_dir, tmp_path / "audit-output", generate_plots_flag=False
    )

    assert result.exit_code == 1
    assert result.verdict == "NOT READY — SIMULATOR OR LABEL CORRECTIONS REQUIRED"


def test_valid_dataset_has_no_structural_findings(tiny_dataset_dir: Path) -> None:
    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)
    findings = check_structural(handle, records)
    assert findings == []


def test_parquet_metadata_matches_manifest_row_counts(tiny_dataset_dir: Path) -> None:
    manifest = json.loads((tiny_dataset_dir / "dataset_manifest.json").read_text())
    telemetry = pq.read_table(tiny_dataset_dir / "telemetry.parquet")
    assert telemetry.num_rows == manifest["row_counts"]["telemetry"]
