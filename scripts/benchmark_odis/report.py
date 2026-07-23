"""Per-run artifact writing and resume-safe claim generation (PR181).

Per-run outputs (`environment.json`/`config.json`/`raw-metrics.json`/
`summary.json`/`report.md`) go under `benchmark-results/<run-id>/`
(gitignored — reproducible from the runner). The consolidated
`docs/release/v1.1-performance-report.md` is written separately by
`__main__.py` from the aggregated `summary.json`s across all runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_run_artifacts(
    run_dir: Path,
    *,
    config: dict[str, Any],
    environment: dict[str, Any],
    raw_metrics: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "config.json", config)
    _write_json(run_dir / "environment.json", environment)
    _write_json(run_dir / "raw-metrics.json", raw_metrics)
    _write_json(run_dir / "summary.json", summary)
    (run_dir / "report.md").write_text(
        render_run_report_md(config=config, environment=environment, summary=summary),
        encoding="utf-8",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def render_run_report_md(
    *,
    config: dict[str, Any],
    environment: dict[str, Any],
    summary: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append(f"# Benchmark run {config.get('run_id')}")
    lines.append("")
    lines.append(
        f"Mode: `{config.get('mode')}` · Scenario: `{config.get('scenario')}` · "
        f"Assets: {config.get('asset_count')} · Duration: "
        f"{config.get('duration_seconds')}s"
    )
    lines.append("")
    lines.append("Local-machine measurement only — not a production or cloud result.")
    lines.append("")
    lines.append("## Environment")
    lines.append("")
    for key in (
        "git_commit",
        "os",
        "cpu_architecture",
        "cpu_model",
        "cpu_count",
        "memory_bytes",
        "docker_version",
        "python_version",
        "model",
        "benchmark_timestamp",
    ):
        lines.append(f"- **{key}**: {environment.get(key)}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary, indent=2, default=str))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def generate_resume_safe_claims(aggregated_summary: dict[str, Any]) -> list[str]:
    """Candidate resume bullets built only from measured fields present in
    the aggregated summary — never production/enterprise/HA/exact-capacity
    language. Returns an empty list (rather than guessing) for any claim
    whose required fields are missing."""
    claims: list[str] = []

    throughput = aggregated_summary.get("throughput")
    if throughput:
        events = throughput.get("total_telemetry_events")
        assets = aggregated_summary.get("max_stable_asset_count")
        rate = throughput.get("telemetry_measurement_events_per_second")
        p95 = aggregated_summary.get("hop_latencies", {}).get(
            "telemetry_acquisition_to_inference_publish_ms", {}
        ).get("p95_ms")
        if events and assets and rate and p95 is not None:
            claims.append(
                f"Processed {events:,} telemetry events across {assets} simulated "
                f"assets at {rate:.1f} events/sec with p95 telemetry-to-inference "
                f"latency of {p95:.0f} ms (local Docker Compose benchmark)."
            )

    reliability = aggregated_summary.get("reliability")
    if reliability and "replayed_event_count" in reliability:
        claims.append(
            "Maintained zero duplicate AI-fault-evidence rows while replaying "
            f"{reliability['replayed_event_count']} previously-processed "
            "alert-transition events (local Docker Compose benchmark)."
        )

    fault_response = aggregated_summary.get("hop_latencies", {}).get(
        "fault_onset_to_recommendation_wall_ms", {}
    )
    has_median = fault_response.get("median_ms") is not None
    has_p95 = fault_response.get("p95_ms") is not None
    if has_median and has_p95:
        claims.append(
            "Reduced fault-onset-to-operator-recommendation time to a median of "
            f"{fault_response['median_ms']:.0f} ms and p95 of "
            f"{fault_response['p95_ms']:.0f} ms in a local Docker Compose "
            "benchmark."
        )

    return claims
