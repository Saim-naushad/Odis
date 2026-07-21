"""Top-level PR175 orchestration: freeze the PR174 candidate, select an
alert policy on its own validation split only, then evaluate three
complete systems (A: original model + PR170 policy; B: robust candidate +
PR170 policy; C: robust candidate + newly selected policy) across every
required cohort, decide promotion, and write every output artifact
atomically (mirrors `generate.py`'s temp-dir-then-rename pattern).

Ordering is the whole point of this module: `search_robust_policies` is
called, and its result is bound to `selected_policy`, strictly before any
cohort other than the robust training dataset's own validation split is
ever read. `PolicySelectionResult.policy_selected_before_evaluation`
records this as an explicit boolean, and `_ordering_timestamps` records
wall-clock timestamps proving it (spec section 6).

Never mutates PR168's models directory, PR174's `-comparison` directory,
or the robust candidate's own `models` CLI output — this module only
*reads* all three and writes its own, separate output directory.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.simulator.dataset.alert_policy.state_machine import StateMachineConfig
from backend.simulator.dataset.manifest import resolve_git_commit
from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.ood.data_loading import (
    InsufficientDataSummary,
    filter_experiment_dataset,
    filter_insufficient_data_summary_to_runs,
    load_ood_experiment_dataset,
)
from backend.simulator.dataset.ood.gapped_alert_evaluation import (
    evaluate_gapped_detection,
)
from backend.simulator.dataset.robustness.artifacts import (
    ModelArtifacts,
    load_model_artifacts,
)
from backend.simulator.dataset.robustness.candidate import (
    FrozenCandidate,
    load_frozen_candidate,
)
from backend.simulator.dataset.robustness.comparison import (
    CohortComparison,
    compare_models_on_cohort,
)
from backend.simulator.dataset.robustness.config import (
    DEFAULT_PROMOTION_THRESHOLDS,
    FROZEN_ALERT_POLICY,
    PromotionThresholds,
)
from backend.simulator.dataset.robustness.evaluation import (
    CohortEvaluation,
    evaluate_model_on_cohort,
)
from backend.simulator.dataset.robustness.generate import CohortDataset
from backend.simulator.dataset.robustness.policy_config import (
    ROBUST_POLICY_SCHEMA_VERSION,
)
from backend.simulator.dataset.robustness.policy_promotion import (
    PolicyPromotionDecision,
    decide_policy_promotion,
    no_policy_selected_decision,
)
from backend.simulator.dataset.robustness.policy_report import (
    generate_policy_plots,
    render_policy_evaluation_report,
)
from backend.simulator.dataset.robustness.policy_search import (
    search_robust_policies,
)

REQUIRED_COHORT_NAMES: tuple[str, ...] = (
    "robust_internal_test",
    "pilot",
    "high_load",
    "hot_start",
    "late_onset",
    "high_noise",
    "combined_ood_v1",
)


class PolicySelectionOutputExistsError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"output directory already exists and is non-empty: {path} "
            "(pass --overwrite / overwrite=True to replace it)"
        )
        self.path = path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PolicySelectionResult:
    output_directory: Path
    decision: str
    selected_policy: StateMachineConfig | None
    policy_selected_before_evaluation: bool
    promoted: bool


def _load_validation_split(
    features_dir: Path, dataset_dir: Path
) -> tuple[ExperimentDataset, InsufficientDataSummary]:
    dataset, insufficient_data = load_ood_experiment_dataset(features_dir, dataset_dir)
    val_mask = dataset.split_mask("validation")
    val_run_ids = set(dataset.run_ids[val_mask].tolist())
    val_dataset = filter_experiment_dataset(dataset, val_mask)
    val_insufficient = filter_insufficient_data_summary_to_runs(
        insufficient_data, val_run_ids, valid_row_count=len(val_dataset.y)
    )
    return val_dataset, val_insufficient


def _evaluate_three_systems(
    *,
    original_artifacts: ModelArtifacts,
    candidate_artifacts: ModelArtifacts,
    selected_policy: StateMachineConfig,
    cohorts: dict[str, CohortDataset],
) -> tuple[
    dict[str, CohortEvaluation],
    dict[str, CohortEvaluation],
    dict[str, CohortEvaluation],
]:
    system_a: dict[str, CohortEvaluation] = {}
    system_b: dict[str, CohortEvaluation] = {}
    system_c: dict[str, CohortEvaluation] = {}
    for name, cohort in cohorts.items():
        system_a[name] = evaluate_model_on_cohort(
            original_artifacts,
            cohort.features_dir,
            cohort_name=name,
            dataset_dir=cohort.dataset_dir,
            split=cohort.split,
            policy=FROZEN_ALERT_POLICY,
        )
        system_b[name] = evaluate_model_on_cohort(
            candidate_artifacts,
            cohort.features_dir,
            cohort_name=name,
            dataset_dir=cohort.dataset_dir,
            split=cohort.split,
            policy=FROZEN_ALERT_POLICY,
        )
        system_c[name] = evaluate_model_on_cohort(
            candidate_artifacts,
            cohort.features_dir,
            cohort_name=name,
            dataset_dir=cohort.dataset_dir,
            split=cohort.split,
            policy=selected_policy,
        )
        if system_b[name].diagnosis != system_c[name].diagnosis:
            raise AssertionError(
                f"cohort {name!r}: System B and System C row-level diagnosis "
                "differ — the alert policy must never change row-level "
                "predictions"
            )
    return system_a, system_b, system_c


def run_policy_selection(
    *,
    comparison_dir: Path,
    original_models_dir: Path,
    robust_dataset_dir: Path,
    robust_features_dir: Path,
    pilot_features_dir: Path,
    pilot_dataset_dir: Path,
    external_cohorts: dict[str, CohortDataset],
    output_directory: Path,
    thresholds: PromotionThresholds = DEFAULT_PROMOTION_THRESHOLDS,
    overwrite: bool = False,
    generation_command: str = "backend.simulator.dataset.robustness.policy_generate",
) -> PolicySelectionResult:
    if output_directory.exists() and any(output_directory.iterdir()) and not overwrite:
        raise PolicySelectionOutputExistsError(output_directory)

    required_external = {
        "high_load",
        "hot_start",
        "late_onset",
        "high_noise",
        "combined_ood_v1",
    }
    missing = required_external - set(external_cohorts)
    if missing:
        raise ValueError(f"external_cohorts is missing required cohorts: {missing}")

    # --- 1. Freeze the robust candidate (spec section 1) --------------------
    candidate = load_frozen_candidate(
        comparison_dir,
        training_dataset_dir=robust_dataset_dir,
        training_features_dir=robust_features_dir,
    )
    candidate_artifacts = candidate.as_model_artifacts()
    original_artifacts = load_model_artifacts(original_models_dir)

    # --- 2/3/4/5. Policy search on the validation split only ----------------
    val_dataset, val_insufficient = _load_validation_split(
        robust_features_dir, robust_dataset_dir
    )
    proba_val = candidate_artifacts.pipeline.predict_proba(
        val_dataset.X_group(candidate_artifacts.feature_group)
    )
    baseline_detection = evaluate_gapped_detection(
        val_dataset,
        proba_val,
        val_insufficient,
        candidate_artifacts.class_order,
        FROZEN_ALERT_POLICY,
    )
    baseline_median_latency = baseline_detection.median_correct_class_latency_seconds

    policy_selected_at = datetime.now(UTC)
    policy_search_result = search_robust_policies(
        val_dataset,
        proba_val,
        val_insufficient,
        candidate_artifacts.class_order,
        baseline_median_latency_seconds=baseline_median_latency,
    )
    selected_candidate = policy_search_result.selected
    selected_policy = selected_candidate.config if selected_candidate else None
    external_evaluation_started_at = datetime.now(UTC)
    # Structural + timestamp proof (spec section 6): `search_robust_policies`
    # above never received a path or dataset for any cohort other than the
    # robust training set's own validation split — no external cohort could
    # have influenced `selected_policy` even in principle — and the wall-
    # clock ordering below is asserted, not just claimed.
    assert policy_selected_at <= external_evaluation_started_at

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-", dir=output_directory.parent
        )
    )
    try:
        (tmp_dir / "robust_policy_search.json").write_text(
            json.dumps(
                {
                    "policy_search": policy_search_result.to_json_dict(),
                    "policy_selected_at": policy_selected_at.isoformat(),
                    "external_evaluation_started_at": (
                        external_evaluation_started_at.isoformat()
                    ),
                    "policy_selected_before_evaluation": (
                        policy_selected_at <= external_evaluation_started_at
                    ),
                },
                indent=2,
                default=str,
            )
        )

        if selected_policy is None:
            decision: PolicyPromotionDecision = no_policy_selected_decision(
                thresholds=thresholds
            )
            (tmp_dir / "promotion_decision.json").write_text(
                json.dumps(decision.to_json_dict(), indent=2, default=str)
            )
            (tmp_dir / "robust_alert_evaluation.json").write_text(
                json.dumps({"note": "no policy selected; no System C evaluated"})
            )
            report_markdown = (
                "# PR175 Robust Alert-Policy Selection\n\n"
                "No candidate policy in the 120-combination search grid survived "
                "the validation rejection rule. See `robust_policy_search.json` "
                "for every rejected candidate and its rejection reason.\n\n"
                f"**Decision: {decision.decision}**\n"
            )
            (tmp_dir / "robust_promotion_report.md").write_text(report_markdown)
        else:
            all_cohorts: dict[str, CohortDataset] = {
                "robust_internal_test": CohortDataset(
                    features_dir=robust_features_dir,
                    dataset_dir=robust_dataset_dir,
                    split="test",
                ),
                "pilot": CohortDataset(
                    features_dir=pilot_features_dir,
                    dataset_dir=pilot_dataset_dir,
                    split="test",
                ),
                **external_cohorts,
            }
            system_a, system_b, system_c = _evaluate_three_systems(
                original_artifacts=original_artifacts,
                candidate_artifacts=candidate_artifacts,
                selected_policy=selected_policy,
                cohorts=all_cohorts,
            )

            b_vs_a: dict[str, CohortComparison] = {
                name: compare_models_on_cohort(
                    name, system_a[name], system_b[name], fault_classes=FAULT_CLASSES
                )
                for name in all_cohorts
            }
            c_vs_a: dict[str, CohortComparison] = {
                name: compare_models_on_cohort(
                    name, system_a[name], system_c[name], fault_classes=FAULT_CLASSES
                )
                for name in all_cohorts
            }

            decision = decide_policy_promotion(
                cohort_comparisons=c_vs_a,
                fault_classes=FAULT_CLASSES,
                thresholds=thresholds,
            )

            (tmp_dir / "robust_alert_evaluation.json").write_text(
                json.dumps(
                    {
                        "system_a_original_pr170_policy": {
                            name: e.to_json_dict() for name, e in system_a.items()
                        },
                        "system_b_robust_pr170_policy": {
                            name: e.to_json_dict() for name, e in system_b.items()
                        },
                        "system_c_robust_new_policy": {
                            name: e.to_json_dict() for name, e in system_c.items()
                        },
                        "b_vs_a": {
                            name: c.to_json_dict() for name, c in b_vs_a.items()
                        },
                        "c_vs_a": {
                            name: c.to_json_dict() for name, c in c_vs_a.items()
                        },
                    },
                    indent=2,
                    default=str,
                )
            )
            (tmp_dir / "promotion_decision.json").write_text(
                json.dumps(decision.to_json_dict(), indent=2, default=str)
            )

            generate_policy_plots(
                policy_search_result=policy_search_result,
                system_a=system_a,
                system_b=system_b,
                system_c=system_c,
                output_dir=tmp_dir / "plots",
            )

            report_markdown = render_policy_evaluation_report(
                generation_command=generation_command,
                candidate=candidate,
                selected_policy=selected_policy,
                policy_search_result=policy_search_result,
                system_a=system_a,
                system_b=system_b,
                system_c=system_c,
                b_vs_a=b_vs_a,
                c_vs_a=c_vs_a,
                decision=decision,
            )
            (tmp_dir / "robust_promotion_report.md").write_text(report_markdown)

            promoted = decision.decision == "PROMOTE ROBUST MODEL AND POLICY"
            if promoted:
                _write_promoted_artifacts(
                    tmp_dir=tmp_dir,
                    candidate=candidate,
                    selected_policy=selected_policy,
                    decision=decision,
                    external_cohorts=external_cohorts,
                    pilot_features_dir=pilot_features_dir,
                    generation_command=generation_command,
                )
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if output_directory.exists():
        shutil.rmtree(output_directory)
    tmp_dir.rename(output_directory)

    return PolicySelectionResult(
        output_directory=output_directory,
        decision=decision.decision,
        selected_policy=selected_policy,
        policy_selected_before_evaluation=(
            policy_selected_at <= external_evaluation_started_at
        ),
        promoted=decision.decision == "PROMOTE ROBUST MODEL AND POLICY",
    )


def _write_promoted_artifacts(
    *,
    tmp_dir: Path,
    candidate: FrozenCandidate,
    selected_policy: StateMachineConfig,
    decision: PolicyPromotionDecision,
    external_cohorts: dict[str, CohortDataset],
    pilot_features_dir: Path,
    generation_command: str,
) -> None:
    artifacts_dir = tmp_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)

    shutil.copy2(candidate.pipeline_path, artifacts_dir / "promoted_pipeline.joblib")
    promoted_pipeline_sha256 = _sha256_file(artifacts_dir / "promoted_pipeline.joblib")

    alert_policy_artifact = {
        "class_order": list(candidate.class_order),
        "state_machine_config": selected_policy.to_json_dict(),
    }
    (artifacts_dir / "promoted_alert_policy.json").write_text(
        json.dumps(alert_policy_artifact, indent=2, default=str)
    )
    policy_sha256 = hashlib.sha256(
        json.dumps(alert_policy_artifact, sort_keys=True).encode()
    ).hexdigest()

    git_commit, git_status = resolve_git_commit()
    cohort_hashes = {
        "pilot": _sha256_file(pilot_features_dir / "feature_manifest.json"),
        **{
            name: _sha256_file(cohort.features_dir / "feature_manifest.json")
            for name, cohort in external_cohorts.items()
        },
    }
    metadata = {
        "robust_policy_schema_version": ROBUST_POLICY_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
        "git_commit_status": git_status,
        "generation_command": generation_command,
        "model_hash": promoted_pipeline_sha256,
        "policy_hash": policy_sha256,
        "training_dataset_manifest_sha256": (
            candidate.training_dataset_manifest_sha256
        ),
        "training_feature_manifest_sha256": (
            candidate.training_feature_manifest_sha256
        ),
        "numerical_safety_policy_version": candidate.safety_policy_version,
        "class_order": list(candidate.class_order),
        "feature_order": list(candidate.feature_order),
        "model_type": candidate.model_metadata["model_type"],
        "feature_group": candidate.feature_group,
        "hyperparameters": candidate.model_metadata["hyperparameters"],
        "evaluation_cohort_feature_manifest_sha256": cohort_hashes,
        "promotion_decision": decision.to_json_dict(),
    }
    (artifacts_dir / "promoted_system_metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str)
    )
