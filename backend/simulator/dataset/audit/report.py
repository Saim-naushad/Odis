"""Orchestrates every check module into one audit run (PR166 spec sections 3-10).

`run_audit` is the single entry point `__main__.py` calls: load the dataset
once, run every check module against the same in-memory records, assemble
`summary.json` (the machine-readable form) and `quality_report.md` (the
human-readable form), and return the process exit status the CLI needs.

Determinism: neither output embeds the audit run's own wall-clock time —
only facts already fixed by dataset generation (the manifest's
`created_at`, row counts, findings computed from the data itself). Running
the audit twice against the same, unchanged dataset directory produces
byte-identical `summary.json` and `quality_report.md`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.simulator.dataset.audit.findings import (
    Finding,
    has_blocking,
    sort_findings,
)
from backend.simulator.dataset.audit.labels import check_labels
from backend.simulator.dataset.audit.leakage import (
    build_feature_exclusion_list,
    check_leakage,
)
from backend.simulator.dataset.audit.loader import DatasetHandle, load_dataset
from backend.simulator.dataset.audit.physical import (
    FAULT_CLASSES,
    MEASUREMENTS,
    check_physical,
)
from backend.simulator.dataset.audit.plots import PlotResult, generate_plots
from backend.simulator.dataset.audit.records import build_records
from backend.simulator.dataset.audit.separability import (
    check_separability,
    compute_separability_summary,
)
from backend.simulator.dataset.audit.structural import check_structural
from backend.simulator.dataset.audit.variation import check_variation
from backend.simulator.dataset.audit.verdict import Verdict, determine_verdict


@dataclass(frozen=True)
class AuditResult:
    dataset_directory: Path
    output_directory: Path
    findings: tuple[Finding, ...]
    verdict: Verdict
    summary_path: Path
    report_path: Path
    plots: tuple[PlotResult, ...]

    @property
    def exit_code(self) -> int:
        return 1 if has_blocking(list(self.findings)) else 0


def run_audit(
    dataset_directory: Path,
    output_directory: Path,
    *,
    generate_plots_flag: bool = True,
) -> AuditResult:
    handle = load_dataset(dataset_directory)
    records = build_records(handle)

    findings: list[Finding] = []
    findings += check_structural(handle, records)
    findings += check_labels(records)

    variation_findings, variation_summary = check_variation(handle, records)
    findings += variation_findings

    (
        physical_findings,
        physical_class_effects,
        physical_signature_results,
    ) = check_physical(records)
    findings += physical_findings

    separability_summary = compute_separability_summary(records)
    findings += check_separability(separability_summary)

    leakage_findings, leakage_notes = check_leakage(handle, records)
    findings += leakage_findings

    findings = sort_findings(findings)
    verdict = determine_verdict(findings)
    feature_exclusion_list = build_feature_exclusion_list()

    output_directory.mkdir(parents=True, exist_ok=True)
    plots: list[PlotResult] = []
    if generate_plots_flag:
        plots = generate_plots(
            handle.spec.sensor_noise,
            handle.splits,
            records,
            output_directory / "plots",
        )

    summary = _build_summary(
        handle=handle,
        findings=findings,
        verdict=verdict,
        variation_summary=variation_summary,
        physical_class_effects=physical_class_effects,
        physical_signature_results=physical_signature_results,
        separability_summary=separability_summary,
        leakage_notes=leakage_notes,
        feature_exclusion_list=feature_exclusion_list,
        plots=plots,
    )
    summary_path = output_directory / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str))

    report_markdown = _render_report(
        handle=handle,
        findings=findings,
        verdict=verdict,
        variation_summary=variation_summary,
        physical_class_effects=physical_class_effects,
        physical_signature_results=physical_signature_results,
        separability_summary=separability_summary,
        leakage_notes=leakage_notes,
        feature_exclusion_list=feature_exclusion_list,
        plots=plots,
    )
    report_path = output_directory / "quality_report.md"
    report_path.write_text(report_markdown)

    return AuditResult(
        dataset_directory=dataset_directory,
        output_directory=output_directory,
        findings=tuple(findings),
        verdict=verdict,
        summary_path=summary_path,
        report_path=report_path,
        plots=tuple(plots),
    )


def _build_summary(
    *,
    handle: DatasetHandle,
    findings: list[Finding],
    verdict: Verdict,
    variation_summary: dict[str, Any],
    physical_class_effects: dict[str, Any],
    physical_signature_results: dict[str, Any],
    separability_summary: dict[str, Any],
    leakage_notes: dict[str, str],
    feature_exclusion_list: list[str],
    plots: list[PlotResult],
) -> dict[str, Any]:
    finding_counts: dict[str, int] = {"blocking": 0, "high": 0, "medium": 0, "low": 0}
    for finding in findings:
        finding_counts[finding.severity] += 1

    return {
        "dataset_id": handle.spec.dataset_id,
        "dataset_directory": str(handle.directory),
        "verdict": verdict,
        "finding_counts": finding_counts,
        "findings": [asdict(finding) for finding in findings],
        "manifest": {
            "row_counts": handle.manifest.get("row_counts"),
            "split_counts": handle.manifest.get("split_counts"),
            "class_distribution": handle.manifest.get("class_distribution"),
            "created_at": handle.manifest.get("created_at"),
            "generation_command": handle.manifest.get("generation_command"),
        },
        "variation": variation_summary,
        "physical": {
            "class_effects": physical_class_effects,
            "signature_results": physical_signature_results,
        },
        "separability": separability_summary,
        "leakage": {
            "notes": leakage_notes,
            "feature_exclusion_list": feature_exclusion_list,
        },
        "plots": [asdict(plot) for plot in plots],
    }


def _findings_by_category(findings: list[Finding], category: str) -> list[Finding]:
    return [f for f in findings if f.category == category]


def _render_finding_lines(findings: list[Finding]) -> list[str]:
    if not findings:
        return ["No issues found.", ""]
    lines = []
    for finding in findings:
        suffix = " (see summary.json for evidence)" if finding.evidence else ""
        lines.append(f"- **[{finding.severity.upper()}]** {finding.message}{suffix}")
    lines.append("")
    return lines


def _render_numeric_table(numeric: dict[str, dict[str, float]]) -> list[str]:
    lines = [
        "| Field | Count | Min | Max | Mean | Stdev | Distinct |",
        "|---|---|---|---|---|---|---|",
    ]
    for field, stats in numeric.items():
        if stats.get("count", 0) == 0:
            lines.append(f"| {field} | 0 | - | - | - | - | - |")
            continue
        lines.append(
            f"| {field} | {stats['count']} | {stats['min']:.4f} | {stats['max']:.4f} "
            f"| {stats['mean']:.4f} | {stats['stdev']:.4f} | {stats['distinct']} |"
        )
    lines.append("")
    return lines


def _render_physical_table(
    class_effects: dict[str, Any], signature_results: dict[str, Any]
) -> list[str]:
    lines: list[str] = []
    for class_label in FAULT_CLASSES:
        lines.append(f"### {class_label}")
        lines.append("")
        lines.append(
            "| Measurement | Median pre | Median active | Median change | "
            "Direction consistency | Signature status |"
        )
        lines.append("|---|---|---|---|---|---|")
        for measurement in MEASUREMENTS:
            effect = class_effects.get(class_label, {}).get(measurement)
            signature_result = signature_results.get(class_label, {}).get(
                measurement, {}
            )
            status = signature_result.get("status", "-")
            if effect is None:
                lines.append(f"| {measurement} | - | - | - | - | {status} |")
                continue
            lines.append(
                f"| {measurement} | {effect['median_pre']:.4f} | "
                f"{effect['median_active']:.4f} | {effect['median_change']:.4f} | "
                f"{effect['direction_consistency']:.0%} | {status} |"
            )
        lines.append("")
    return lines


def _render_separability_table(threshold_separability: dict[str, Any]) -> list[str]:
    lines = ["| Class | Measurement | Overall balanced accuracy |", "|---|---|---|"]
    for class_label in FAULT_CLASSES:
        for measurement in MEASUREMENTS:
            result = threshold_separability.get(class_label, {}).get(measurement)
            if result is None:
                continue
            lines.append(
                f"| {class_label} | {measurement} | "
                f"{result['overall_balanced_accuracy']:.3f} |"
            )
    lines.append("")
    return lines


def _render_report(
    *,
    handle: DatasetHandle,
    findings: list[Finding],
    verdict: Verdict,
    variation_summary: dict[str, Any],
    physical_class_effects: dict[str, Any],
    physical_signature_results: dict[str, Any],
    separability_summary: dict[str, Any],
    leakage_notes: dict[str, str],
    feature_exclusion_list: list[str],
    plots: list[PlotResult],
) -> str:
    lines: list[str] = []
    lines.append(f"# Dataset Quality Report — {handle.spec.dataset_id}")
    lines.append("")
    lines.append(f"**Verdict: {verdict}**")
    lines.append("")
    lines.append("## Dataset overview")
    lines.append("")
    lines.append(f"- Dataset ID: `{handle.spec.dataset_id}`")
    lines.append(f"- Schema version: `{handle.manifest.get('schema_version')}`")
    lines.append(f"- Simulator version: `{handle.spec.simulator_version}`")
    lines.append(
        "- Generated at (dataset generation, not audit time): "
        f"{handle.manifest.get('created_at')}"
    )
    lines.append(
        f"- Generation command: `{handle.manifest.get('generation_command')}`"
    )
    row_counts = handle.manifest.get("row_counts", {})
    lines.append(
        f"- Rows: runs={row_counts.get('runs')}, "
        f"telemetry={row_counts.get('telemetry')}, "
        f"ground_truth={row_counts.get('ground_truth')}"
    )
    split_counts = handle.manifest.get("split_counts", {})
    lines.append(
        f"- Splits: train={split_counts.get('train')}, "
        f"validation={split_counts.get('validation')}, test={split_counts.get('test')}"
    )
    lines.append(f"- Class distribution: {handle.manifest.get('class_distribution')}")
    lines.append("")

    lines.append("## 1. Structural validation")
    lines.append("")
    lines += _render_finding_lines(_findings_by_category(findings, "structural"))

    lines.append("## 2. Label integrity")
    lines.append("")
    lines += _render_finding_lines(_findings_by_category(findings, "labeling"))

    lines.append("## 3. Variation analysis")
    lines.append("")
    lines += _render_numeric_table(variation_summary["numeric"])
    lines.append(f"- Class counts: {variation_summary['class_counts']}")
    lines.append(f"- Target-asset counts: {variation_summary['target_asset_counts']}")
    lines.append(f"- Split counts: {variation_summary['split_counts']}")
    lines.append("")
    lines += _render_finding_lines(_findings_by_category(findings, "variation"))

    lines.append("## 4. Physical-behavior analysis")
    lines.append("")
    lines += _render_physical_table(physical_class_effects, physical_signature_results)
    lines += _render_finding_lines(_findings_by_category(findings, "physical"))

    lines.append("## 5. Separability analysis")
    lines.append("")
    lines += _render_separability_table(separability_summary["threshold_separability"])
    lines += _render_finding_lines(_findings_by_category(findings, "separability"))

    lines.append("## 6. Leakage audit")
    lines.append("")
    lines.append("| Candidate source | Assessment |")
    lines.append("|---|---|")
    for source, note in leakage_notes.items():
        lines.append(f"| {source} | {note} |")
    lines.append("")
    lines.append("**Future feature-exclusion list** (never feed these `runs.parquet` "
                 "columns to a model — they encode the label or run bookkeeping):")
    lines.append("")
    for column in feature_exclusion_list:
        lines.append(f"- `{column}`")
    lines.append("")
    lines += _render_finding_lines(_findings_by_category(findings, "leakage"))

    lines.append("## 7. Plots")
    lines.append("")
    if not plots:
        lines.append(
            "No plots generated — install the `dataset-analysis` optional "
            "dependency (`pip install -e \".[dataset-analysis]\"`) to enable "
            "plotting."
        )
        lines.append("")
    for plot in plots:
        lines.append(f"### {plot.title}")
        lines.append("")
        lines.append(f"![{plot.title}](plots/{plot.filename})")
        lines.append("")
        lines.append(plot.caption)
        lines.append("")

    lines.append("## 8. Quality verdict")
    lines.append("")
    lines.append(f"**{verdict}**")
    lines.append("")
    for severity in ("blocking", "high", "medium", "low"):
        by_severity = [f for f in findings if f.severity == severity]
        lines.append(f"### {severity.capitalize()} ({len(by_severity)})")
        lines.append("")
        lines += _render_finding_lines(by_severity)

    return "\n".join(lines) + "\n"
