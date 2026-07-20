"""Top-level PR172 orchestration: load already-computed PR171 evaluation
outputs for the combined OOD cohort and every isolated-shift cohort,
compute per-shift damage/rankings/classification, run the interaction and
invalid-row analyses, and write every output artifact atomically (mirrors
`ood/generate.py`'s temp-dir-then-rename pattern).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.shift_study.audit_loading import (
    CohortAudit,
    load_cohort_audit,
)
from backend.simulator.dataset.shift_study.cohort_loading import load_cohorts
from backend.simulator.dataset.shift_study.interaction_analysis import (
    analyze_interactions,
)
from backend.simulator.dataset.shift_study.invalid_rows import aggregate_invalid_rows
from backend.simulator.dataset.shift_study.plots import generate_plots
from backend.simulator.dataset.shift_study.rankings import (
    compute_shift_damage,
    rank_shifts,
)
from backend.simulator.dataset.shift_study.report import (
    build_cohort_metrics_json,
    build_cohort_rankings_json,
    build_shift_study_summary,
    render_markdown_report,
)
from backend.simulator.dataset.shift_study.representative_cases import (
    select_study_cases,
)
from backend.simulator.dataset.shift_study.verdict import determine_study_verdict

_COMBINED_COHORT_NAME = "combined"


class ShiftStudyOutputExistsError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"output directory already exists and is non-empty: {path} "
            "(pass --overwrite / overwrite=True to replace it)"
        )
        self.path = path


@dataclass(frozen=True)
class ShiftStudyResult:
    output_directory: Path
    primary_failure: str | None
    recommendation: str


def run_shift_study(
    *,
    combined_ood_evaluation: Path | None,
    cohort_evaluations: Sequence[tuple[str, Path]],
    cohort_audits: Sequence[tuple[str, Path]] = (),
    output_directory: Path,
    overwrite: bool = False,
    generation_command: str = "backend.simulator.dataset.shift_study",
) -> ShiftStudyResult:
    if output_directory.exists() and any(output_directory.iterdir()) and not overwrite:
        raise ShiftStudyOutputExistsError(output_directory)

    named_dirs: list[tuple[str, Path]] = list(cohort_evaluations)
    if combined_ood_evaluation is not None:
        named_dirs = [(_COMBINED_COHORT_NAME, combined_ood_evaluation), *named_dirs]
    cohorts = load_cohorts(named_dirs)

    isolated_names = [name for name, _ in cohort_evaluations]
    combined_name = (
        _COMBINED_COHORT_NAME if combined_ood_evaluation is not None else None
    )

    damages = {
        name: compute_shift_damage(name, cohort, fault_classes=FAULT_CLASSES)
        for name, cohort in cohorts.items()
    }
    isolated_damages = {name: damages[name] for name in isolated_names}
    combined_damage = damages.get(combined_name) if combined_name else None

    rankings = rank_shifts(isolated_damages)
    invalid_rows = aggregate_invalid_rows(cohorts)
    interaction = analyze_interactions(
        combined_damage=combined_damage,
        isolated_damages=isolated_damages,
        cohorts=cohorts,
    )
    study_verdict = determine_study_verdict(isolated_damages, interaction, invalid_rows)

    audits: dict[str, CohortAudit] = {
        name: load_cohort_audit(path) for name, path in cohort_audits
    }
    study_cases = select_study_cases(cohorts)

    reference_fingerprint = next(iter(cohorts.values())).artifact_fingerprint()

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-", dir=output_directory.parent
        )
    )
    try:
        plots_dir = tmp_dir / "plots"
        plots = generate_plots(
            damages=damages,
            cohorts=cohorts,
            fault_classes=FAULT_CLASSES,
            study_cases=study_cases,
            output_dir=plots_dir,
        )

        summary = build_shift_study_summary(
            generation_command=generation_command,
            reference_fingerprint=reference_fingerprint,
            combined_name=combined_name,
            isolated_names=isolated_names,
            rankings=rankings,
            interaction=interaction,
            verdict=study_verdict,
        )
        (tmp_dir / "shift_study_summary.json").write_text(
            json.dumps(summary, indent=2, default=str)
        )

        cohort_metrics = build_cohort_metrics_json(
            cohorts, damages, audits, study_cases
        )
        (tmp_dir / "cohort_metrics.json").write_text(
            json.dumps(cohort_metrics, indent=2, default=str)
        )

        cohort_rankings = build_cohort_rankings_json(damages, rankings)
        (tmp_dir / "cohort_rankings.json").write_text(
            json.dumps(cohort_rankings, indent=2, default=str)
        )

        (tmp_dir / "invalid_feature_rows.json").write_text(
            json.dumps(invalid_rows, indent=2, default=str)
        )

        report_markdown = render_markdown_report(
            generation_command=generation_command,
            damages=isolated_damages,
            combined_damage=combined_damage,
            rankings=rankings,
            interaction=interaction,
            verdict=study_verdict,
            invalid_rows=invalid_rows,
            audits=audits,
            plots=plots,
        )
        (tmp_dir / "shift_study_report.md").write_text(report_markdown)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if output_directory.exists():
        shutil.rmtree(output_directory)
    tmp_dir.rename(output_directory)

    return ShiftStudyResult(
        output_directory=output_directory,
        primary_failure=study_verdict.primary_failure,
        recommendation=study_verdict.recommendation,
    )
