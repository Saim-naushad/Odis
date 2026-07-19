"""Plot generation (PR166 spec sections 9 and 11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.simulator.dataset.audit import plots as plots_module
from backend.simulator.dataset.audit.loader import load_dataset
from backend.simulator.dataset.audit.records import build_records
from backend.simulator.dataset.audit.report import run_audit


@pytest.mark.skipif(
    not plots_module.MATPLOTLIB_AVAILABLE,
    reason="requires the dataset-analysis optional dependency (matplotlib)",
)
def test_generate_plots_writes_expected_files(
    tmp_path: Path, tiny_dataset_dir: Path
) -> None:
    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)
    output_dir = tmp_path / "plots"

    results = plots_module.generate_plots(
        handle.spec.sensor_noise, handle.splits, records, output_dir
    )

    assert results
    for result in results:
        assert (output_dir / result.filename).is_file()
        assert result.title
        assert result.caption


def test_generate_plots_returns_empty_when_matplotlib_unavailable(
    tmp_path: Path, tiny_dataset_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plots_module, "MATPLOTLIB_AVAILABLE", False)
    handle = load_dataset(tiny_dataset_dir)
    records = build_records(handle)

    results = plots_module.generate_plots(
        handle.spec.sensor_noise, handle.splits, records, tmp_path / "plots"
    )

    assert results == []
    assert not (tmp_path / "plots").exists()


def test_run_audit_notes_skipped_plots_in_report(
    tmp_path: Path, tiny_dataset_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plots_module, "MATPLOTLIB_AVAILABLE", False)

    result = run_audit(tiny_dataset_dir, tmp_path / "audit-output")

    assert result.plots == ()
    report_text = result.report_path.read_text()
    assert "No plots generated" in report_text
