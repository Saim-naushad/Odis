"""Top-level PR174 orchestration: load the original PR168 and robust
candidate model artifacts, score both across every evaluation cohort
through the identical metric code path, compare, decide promotion, and
write every output artifact atomically (mirrors `models/generate.py`'s
temp-dir-then-rename pattern).

Never mutates the original PR168 artifact directory or the robust
candidate's own `models` CLI output — this module only *reads* both and
writes its own, separate `robust_candidate_*`/`promotion_decision.json`
artifacts.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.robustness.artifacts import (
    ModelArtifacts,
    load_model_artifacts,
)
from backend.simulator.dataset.robustness.comparison import (
    CohortComparison,
    compare_models_on_cohort,
)
from backend.simulator.dataset.robustness.config import (
    DEFAULT_PROMOTION_THRESHOLDS,
    EXTERNAL_COHORT_NAMES,
    ROBUSTNESS_SCHEMA_VERSION,
    PromotionThresholds,
)
from backend.simulator.dataset.robustness.evaluation import (
    CohortEvaluation,
    evaluate_model_on_cohort,
)
from backend.simulator.dataset.robustness.promotion import (
    decide_promotion,
)
from backend.simulator.dataset.robustness.report import render_evaluation_report


class RobustnessOutputExistsError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"output directory already exists and is non-empty: {path} "
            "(pass --overwrite / overwrite=True to replace it)"
        )
        self.path = path


@dataclass(frozen=True)
class CohortDataset:
    """Where one cohort's features/source dataset live.

    `split=None` (the default, and every PR174 external-cohort use) scores
    the entire cohort dataset. PR175 also uses this type for the pilot and
    robust-internal-test cohorts, both of which set `split="test"` to
    narrow to a held-out split first — see `evaluation.
    evaluate_model_on_cohort`'s own `split` parameter, which this maps to
    directly.
    """

    features_dir: Path
    dataset_dir: Path | None = None
    split: str | None = None


@dataclass(frozen=True)
class RobustnessComparisonResult:
    output_directory: Path
    decision: str
    high_noise_balanced_accuracy_gain: float
    combined_ood_balanced_accuracy_gain: float
    pilot_balanced_accuracy_drop: float


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_robustness_comparison(
    *,
    original_models_dir: Path,
    robust_models_dir: Path,
    robust_features_dir: Path,
    robust_dataset_dir: Path,
    pilot_features_dir: Path,
    pilot_dataset_dir: Path,
    external_cohorts: dict[str, CohortDataset],
    output_directory: Path,
    thresholds: PromotionThresholds = DEFAULT_PROMOTION_THRESHOLDS,
    overwrite: bool = False,
    generation_command: str = "backend.simulator.dataset.robustness",
) -> RobustnessComparisonResult:
    if output_directory.exists() and any(output_directory.iterdir()) and not overwrite:
        raise RobustnessOutputExistsError(output_directory)

    missing = set(EXTERNAL_COHORT_NAMES) - {"pilot", *external_cohorts}
    if missing:
        raise ValueError(f"external_cohorts is missing required cohorts: {missing}")

    original_artifacts = load_model_artifacts(original_models_dir)
    robust_artifacts = load_model_artifacts(robust_models_dir)

    internal_original = evaluate_model_on_cohort(
        original_artifacts,
        pilot_features_dir,
        dataset_dir=pilot_dataset_dir,
        split="test",
        cohort_name="internal_test_original",
    )
    internal_robust = evaluate_model_on_cohort(
        robust_artifacts,
        robust_features_dir,
        dataset_dir=robust_dataset_dir,
        split="test",
        cohort_name="internal_test_robust",
    )

    original_evaluations: dict[str, CohortEvaluation] = {"pilot": internal_original}
    robust_evaluations: dict[str, CohortEvaluation] = {
        "pilot": evaluate_model_on_cohort(
            robust_artifacts,
            pilot_features_dir,
            dataset_dir=pilot_dataset_dir,
            split="test",
            cohort_name="pilot",
        )
    }
    for name, cohort in external_cohorts.items():
        original_evaluations[name] = evaluate_model_on_cohort(
            original_artifacts,
            cohort.features_dir,
            dataset_dir=cohort.dataset_dir,
            cohort_name=name,
        )
        robust_evaluations[name] = evaluate_model_on_cohort(
            robust_artifacts,
            cohort.features_dir,
            dataset_dir=cohort.dataset_dir,
            cohort_name=name,
        )

    cohort_comparisons: dict[str, CohortComparison] = {
        name: compare_models_on_cohort(
            name,
            original_evaluations[name],
            robust_evaluations[name],
            fault_classes=FAULT_CLASSES,
        )
        for name in EXTERNAL_COHORT_NAMES
    }

    decision = decide_promotion(
        cohort_comparisons=cohort_comparisons,
        fault_classes=FAULT_CLASSES,
        thresholds=thresholds,
    )

    training_summary = _build_training_summary(
        original_artifacts=original_artifacts,
        robust_artifacts=robust_artifacts,
        robust_dataset_dir=robust_dataset_dir,
        robust_features_dir=robust_features_dir,
        external_cohorts=external_cohorts,
        pilot_features_dir=pilot_features_dir,
        internal_robust=internal_robust,
        internal_original=internal_original,
    )

    report_markdown = render_evaluation_report(
        generation_command=generation_command,
        original_artifacts=original_artifacts,
        robust_artifacts=robust_artifacts,
        internal_original=internal_original,
        internal_robust=internal_robust,
        cohort_comparisons=cohort_comparisons,
        decision=decision,
    )

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-", dir=output_directory.parent
        )
    )
    try:
        shutil.copy2(
            robust_artifacts.pipeline_path, tmp_dir / "robust_candidate_pipeline.joblib"
        )
        (tmp_dir / "robust_candidate_metadata.json").write_text(
            json.dumps(robust_artifacts.to_json_dict(), indent=2, default=str)
        )
        (tmp_dir / "robust_training_summary.json").write_text(
            json.dumps(training_summary, indent=2, default=str)
        )
        (tmp_dir / "robust_evaluation_report.md").write_text(report_markdown)
        (tmp_dir / "promotion_decision.json").write_text(
            json.dumps(decision.to_json_dict(), indent=2, default=str)
        )
        (tmp_dir / "cohort_comparisons.json").write_text(
            json.dumps(
                {name: c.to_json_dict() for name, c in cohort_comparisons.items()},
                indent=2,
                default=str,
            )
        )
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if output_directory.exists():
        shutil.rmtree(output_directory)
    tmp_dir.rename(output_directory)

    pilot_comparison = cohort_comparisons["pilot"]
    high_noise_comparison = cohort_comparisons["high_noise"]
    combined_ood_comparison = cohort_comparisons["combined_ood_v1"]
    return RobustnessComparisonResult(
        output_directory=output_directory,
        decision=decision.decision,
        high_noise_balanced_accuracy_gain=(
            high_noise_comparison.balanced_accuracy.absolute_change or 0.0
        ),
        combined_ood_balanced_accuracy_gain=(
            combined_ood_comparison.balanced_accuracy.absolute_change or 0.0
        ),
        pilot_balanced_accuracy_drop=-(
            pilot_comparison.balanced_accuracy.absolute_change or 0.0
        ),
    )


def _build_training_summary(
    *,
    original_artifacts: ModelArtifacts,
    robust_artifacts: ModelArtifacts,
    robust_dataset_dir: Path,
    robust_features_dir: Path,
    external_cohorts: dict[str, CohortDataset],
    pilot_features_dir: Path,
    internal_robust: CohortEvaluation,
    internal_original: CohortEvaluation,
) -> dict[str, Any]:
    cohort_feature_manifest_hashes = {
        "pilot": _sha256_file(pilot_features_dir / "feature_manifest.json"),
        **{
            name: _sha256_file(cohort.features_dir / "feature_manifest.json")
            for name, cohort in external_cohorts.items()
        },
    }
    return {
        "robustness_schema_version": ROBUSTNESS_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "training_dataset_manifest_sha256": _sha256_file(
            robust_dataset_dir / "dataset_manifest.json"
        ),
        "training_feature_manifest_sha256": _sha256_file(
            robust_features_dir / "feature_manifest.json"
        ),
        "original_model": original_artifacts.to_json_dict(),
        "robust_model": robust_artifacts.to_json_dict(),
        "class_order": list(robust_artifacts.class_order),
        "feature_order": list(robust_artifacts.model_metadata["feature_columns"]),
        "pr173_safety_policy_version": robust_artifacts.model_metadata.get(
            "source_feature_schema_version"
        ),
        "evaluation_cohort_feature_manifest_sha256": cohort_feature_manifest_hashes,
        "internal_test_results": {
            "original_pilot_test": internal_original.to_json_dict(),
            "robust_training_test": internal_robust.to_json_dict(),
        },
    }
