"""Loads and verifies the exact PR174 robust-training candidate artifact
(PR175 spec section 1).

Never refits or regenerates anything as a fallback — every check below
either passes against the frozen `datasets/pem-faults-robust-training-v1-
comparison/` record PR174 produced, or raises a specific, named error.
This is a stricter contract than `artifacts.load_model_artifacts` (which
only checks a model artifact's *internal* self-consistency): here the
pipeline file, its metadata, and the separate `robust_training_summary.
json` PR174 wrote must all agree with each other and with the training
dataset/feature artifacts still on disk, byte-for-byte.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
from sklearn.pipeline import Pipeline

from backend.simulator.dataset.features.config import FEATURE_SCHEMA_VERSION
from backend.simulator.dataset.models.feature_groups import FEATURE_GROUPS
from backend.simulator.dataset.robustness.artifacts import ModelArtifacts


class CandidateArtifactNotFoundError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"required PR174 candidate artifact not found: {path} — run "
            "the PR174 robustness comparison before selecting a policy for "
            "it (this loader never trains or regenerates a fallback)"
        )
        self.path = path


class CandidateArtifactMismatchError(Exception):
    """Raised whenever a recomputed hash, feature order, class order, or
    schema version does not match what PR174's own frozen record says it
    should be — never silently tolerated."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise CandidateArtifactNotFoundError(path)


@dataclass(frozen=True)
class FrozenCandidate:
    pipeline: Pipeline
    pipeline_path: Path
    pipeline_sha256: str
    feature_group: str
    class_order: tuple[str, ...]
    feature_order: tuple[str, ...]
    model_metadata: dict[str, Any]
    training_summary: dict[str, Any]
    training_dataset_manifest_sha256: str
    training_feature_manifest_sha256: str
    safety_policy_version: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "pipeline_path": str(self.pipeline_path),
            "pipeline_sha256": self.pipeline_sha256,
            "model_type": self.model_metadata["model_type"],
            "feature_group": self.feature_group,
            "hyperparameters": self.model_metadata["hyperparameters"],
            "class_order": list(self.class_order),
            "feature_order": list(self.feature_order),
            "training_dataset_manifest_sha256": (
                self.training_dataset_manifest_sha256
            ),
            "training_feature_manifest_sha256": (
                self.training_feature_manifest_sha256
            ),
            "safety_policy_version": self.safety_policy_version,
            "source_dataset_id": self.model_metadata["source_dataset_id"],
        }

    def as_model_artifacts(self) -> ModelArtifacts:
        """Adapts to `artifacts.ModelArtifacts`'s shape so this candidate
        can be scored via `evaluation.evaluate_model_on_cohort` unchanged —
        the two types carry the same pipeline/feature_group/class_order,
        just with different provenance-tracking fields around them."""
        return ModelArtifacts(
            pipeline=self.pipeline,
            pipeline_path=self.pipeline_path,
            pipeline_sha256=self.pipeline_sha256,
            model_metadata=self.model_metadata,
            feature_group=self.feature_group,
            class_order=self.class_order,
        )


def load_frozen_candidate(
    comparison_dir: Path,
    *,
    training_dataset_dir: Path,
    training_features_dir: Path,
) -> FrozenCandidate:
    """Load and cross-verify PR174's `robust_candidate_pipeline.joblib`,
    `robust_candidate_metadata.json`, and `robust_training_summary.json`
    against each other and against the training dataset/feature artifacts
    still on disk at `training_dataset_dir`/`training_features_dir`.
    """
    pipeline_path = comparison_dir / "robust_candidate_pipeline.joblib"
    metadata_path = comparison_dir / "robust_candidate_metadata.json"
    summary_path = comparison_dir / "robust_training_summary.json"
    dataset_manifest_path = training_dataset_dir / "dataset_manifest.json"
    feature_manifest_path = training_features_dir / "feature_manifest.json"

    for path in (
        pipeline_path,
        metadata_path,
        summary_path,
        dataset_manifest_path,
        feature_manifest_path,
    ):
        _require_file(path)

    metadata = json.loads(metadata_path.read_text())
    summary = json.loads(summary_path.read_text())

    # --- model hash ----------------------------------------------------
    pipeline_sha256 = _sha256_file(pipeline_path)
    if pipeline_sha256 != metadata.get("pipeline_sha256"):
        raise CandidateArtifactMismatchError(
            f"robust_candidate_pipeline.joblib's sha256 ({pipeline_sha256}) "
            "does not match robust_candidate_metadata.json's recorded "
            f"pipeline_sha256 ({metadata.get('pipeline_sha256')})"
        )

    # --- training-dataset hash -------------------------------------------
    dataset_manifest_sha256 = _sha256_file(dataset_manifest_path)
    expected_dataset_hash = summary.get("training_dataset_manifest_sha256")
    if dataset_manifest_sha256 != expected_dataset_hash:
        raise CandidateArtifactMismatchError(
            f"{dataset_manifest_path}'s sha256 ({dataset_manifest_sha256}) does "
            "not match robust_training_summary.json's recorded "
            f"training_dataset_manifest_sha256 ({expected_dataset_hash}) — the "
            "robust training dataset on disk has changed since PR174 froze "
            "this candidate"
        )

    # --- feature manifest hash --------------------------------------------
    feature_manifest_sha256 = _sha256_file(feature_manifest_path)
    expected_feature_hash = summary.get("training_feature_manifest_sha256")
    if feature_manifest_sha256 != expected_feature_hash:
        raise CandidateArtifactMismatchError(
            f"{feature_manifest_path}'s sha256 ({feature_manifest_sha256}) does "
            "not match robust_training_summary.json's recorded "
            f"training_feature_manifest_sha256 ({expected_feature_hash}) — the "
            "robust feature dataset on disk has changed since PR174 froze "
            "this candidate"
        )

    # --- feature order / schema version -----------------------------------
    feature_group = metadata["feature_group"]
    if feature_group not in FEATURE_GROUPS:
        raise CandidateArtifactMismatchError(
            f"robust_candidate_metadata.json's feature_group is "
            f"{feature_group!r}, not one of the known groups "
            f"{sorted(FEATURE_GROUPS)}"
        )
    feature_order = tuple(summary.get("feature_order", []))
    if list(feature_order) != FEATURE_GROUPS[feature_group]:
        raise CandidateArtifactMismatchError(
            "robust_training_summary.json's feature_order does not match "
            f"models.feature_groups.FEATURE_GROUPS[{feature_group!r}] — this "
            "candidate was built against a different feature schema than "
            "this codebase currently defines"
        )
    source_schema_version = metadata.get("source_feature_schema_version")
    if source_schema_version != FEATURE_SCHEMA_VERSION:
        raise CandidateArtifactMismatchError(
            "robust_candidate_metadata.json's source_feature_schema_version "
            f"({source_schema_version!r}) does not match this codebase's "
            f"features.config.FEATURE_SCHEMA_VERSION ({FEATURE_SCHEMA_VERSION!r})"
        )
    safety_policy_version = summary.get("pr173_safety_policy_version")
    if safety_policy_version != FEATURE_SCHEMA_VERSION:
        raise CandidateArtifactMismatchError(
            "robust_training_summary.json's pr173_safety_policy_version "
            f"({safety_policy_version!r}) does not match this codebase's "
            f"features.config.FEATURE_SCHEMA_VERSION ({FEATURE_SCHEMA_VERSION!r})"
        )

    # --- pipeline load + class order ---------------------------------------
    pipeline = joblib.load(pipeline_path)
    if "classifier" not in pipeline.named_steps:
        raise CandidateArtifactMismatchError(
            "robust_candidate_pipeline.joblib has no 'classifier' step — "
            "cannot derive predict_proba's class order"
        )
    class_order = tuple(pipeline.named_steps["classifier"].classes_)
    recorded_class_order = tuple(metadata.get("class_order", []))
    if class_order != recorded_class_order:
        raise CandidateArtifactMismatchError(
            f"selected_pipeline.joblib's fitted class order {class_order} "
            "does not match robust_candidate_metadata.json's recorded "
            f"class_order {recorded_class_order}"
        )

    return FrozenCandidate(
        pipeline=pipeline,
        pipeline_path=pipeline_path,
        pipeline_sha256=pipeline_sha256,
        feature_group=feature_group,
        class_order=class_order,
        feature_order=feature_order,
        model_metadata=metadata,
        training_summary=summary,
        training_dataset_manifest_sha256=dataset_manifest_sha256,
        training_feature_manifest_sha256=feature_manifest_sha256,
        safety_policy_version=safety_policy_version,
    )
