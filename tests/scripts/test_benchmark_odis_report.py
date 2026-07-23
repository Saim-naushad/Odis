"""Unit tests for scripts.benchmark_odis.report — no live services."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.benchmark_odis.report import (
    generate_resume_safe_claims,
    render_run_report_md,
    write_run_artifacts,
)


def test_write_run_artifacts_creates_isolated_output_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    write_run_artifacts(
        run_dir,
        config={"run_id": "run-a"},
        environment={"os": "Darwin"},
        raw_metrics={"count": 1},
        summary={"ok": True},
    )
    assert (run_dir / "config.json").exists()
    assert (run_dir / "environment.json").exists()
    assert (run_dir / "raw-metrics.json").exists()
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "report.md").exists()

    assert json.loads((run_dir / "summary.json").read_text()) == {"ok": True}


def test_write_run_artifacts_does_not_leak_into_a_sibling_run_directory(
    tmp_path: Path,
) -> None:
    write_run_artifacts(
        tmp_path / "run-a",
        config={"run_id": "run-a"},
        environment={},
        raw_metrics={},
        summary={"marker": "a"},
    )
    write_run_artifacts(
        tmp_path / "run-b",
        config={"run_id": "run-b"},
        environment={},
        raw_metrics={},
        summary={"marker": "b"},
    )
    a_summary = json.loads((tmp_path / "run-a" / "summary.json").read_text())
    b_summary = json.loads((tmp_path / "run-b" / "summary.json").read_text())
    assert a_summary["marker"] == "a"
    assert b_summary["marker"] == "b"


def test_render_run_report_md_includes_environment_and_summary() -> None:
    markdown = render_run_report_md(
        config={
            "run_id": "run-a",
            "mode": "performance",
            "scenario": "cooling_degradation",
            "asset_count": 1,
            "duration_seconds": 60,
        },
        environment={"os": "Darwin", "git_commit": "abc123"},
        summary={"hop_latencies": {}},
    )
    assert "run-a" in markdown
    assert "abc123" in markdown
    assert "Local-machine measurement only" in markdown


def test_generate_resume_safe_claims_returns_empty_when_fields_missing() -> None:
    assert generate_resume_safe_claims({}) == []


def test_generate_resume_safe_claims_never_divides_by_zero() -> None:
    summary = {
        "throughput": {
            "total_telemetry_events": 0,
            "telemetry_measurement_events_per_second": 0,
        },
        "max_stable_asset_count": 0,
    }
    # Must not raise even though every numeric field is falsy/zero.
    assert generate_resume_safe_claims(summary) == []


def test_generate_resume_safe_claims_builds_throughput_claim_when_measured() -> None:
    summary = {
        "throughput": {
            "total_telemetry_events": 12345,
            "telemetry_measurement_events_per_second": 42.5,
        },
        "max_stable_asset_count": 10,
        "hop_latencies": {
            "telemetry_acquisition_to_inference_publish_ms": {"p95_ms": 87.0},
        },
    }
    claims = generate_resume_safe_claims(summary)
    assert len(claims) == 1
    assert "12,345" in claims[0]
    assert "10 simulated" in claims[0]
    assert "42.5 events/sec" in claims[0]
    assert "87" in claims[0]


def test_generate_resume_safe_claims_never_claims_production_scale() -> None:
    summary = {
        "throughput": {
            "total_telemetry_events": 12345,
            "telemetry_measurement_events_per_second": 42.5,
        },
        "max_stable_asset_count": 10,
        "hop_latencies": {
            "telemetry_acquisition_to_inference_publish_ms": {"p95_ms": 87.0},
        },
    }
    banned_words = ("production", "enterprise", "high availability", "cloud scale")
    for claim in generate_resume_safe_claims(summary):
        lowered = claim.lower()
        for banned_word in banned_words:
            assert banned_word not in lowered
