"""End-to-end audit behavior on a valid tiny dataset: file output, exit
code, determinism, and the CLI (PR166 spec section 11)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.simulator.dataset.audit.__main__ import main as cli_main
from backend.simulator.dataset.audit.loader import DatasetNotFoundError
from backend.simulator.dataset.audit.report import run_audit


def test_audit_produces_expected_output_files(
    tmp_path: Path, tiny_dataset_dir: Path
) -> None:
    result = run_audit(tiny_dataset_dir, tmp_path / "audit-output")

    assert result.summary_path.exists()
    assert result.report_path.exists()
    assert result.summary_path.name == "summary.json"
    assert result.report_path.name == "quality_report.md"


def test_valid_dataset_has_no_blocking_findings(
    tmp_path: Path, tiny_dataset_dir: Path
) -> None:
    result = run_audit(tiny_dataset_dir, tmp_path / "audit-output")

    blocking = [f for f in result.findings if f.severity == "blocking"]
    assert blocking == []
    assert result.exit_code == 0


def test_summary_json_is_valid_and_has_expected_keys(
    tmp_path: Path, tiny_dataset_dir: Path
) -> None:
    result = run_audit(tiny_dataset_dir, tmp_path / "audit-output")
    summary = json.loads(result.summary_path.read_text())

    for key in (
        "dataset_id",
        "verdict",
        "finding_counts",
        "findings",
        "variation",
        "physical",
        "separability",
        "leakage",
        "plots",
    ):
        assert key in summary


def test_audit_is_deterministic_across_runs(
    tmp_path: Path, tiny_dataset_dir: Path
) -> None:
    first = run_audit(tiny_dataset_dir, tmp_path / "audit-1")
    second = run_audit(tiny_dataset_dir, tmp_path / "audit-2")

    assert first.summary_path.read_text() == second.summary_path.read_text()
    assert first.report_path.read_text() == second.report_path.read_text()


def test_cli_success_reports_verdict_and_zero_exit(
    tmp_path: Path, tiny_dataset_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli_main(
        ["--dataset", str(tiny_dataset_dir), "--output", str(tmp_path / "audit-output")]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "verdict:" in out
    assert (tmp_path / "audit-output" / "quality_report.md").exists()


def test_cli_missing_dataset_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli_main(
        [
            "--dataset",
            str(tmp_path / "does-not-exist"),
            "--output",
            str(tmp_path / "audit-output"),
        ]
    )

    assert exit_code != 0
    err = capsys.readouterr().err
    assert "missing required dataset file" in err


def test_load_missing_dataset_raises(tmp_path: Path) -> None:
    with pytest.raises(DatasetNotFoundError):
        run_audit(tmp_path / "does-not-exist", tmp_path / "audit-output")
