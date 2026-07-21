"""Loads a frozen model artifact (either the original PR168 selection or a
PR174 robust-training candidate) for comparison evaluation.

Deliberately more permissive than `ood.artifacts.load_frozen_artifacts`:
that loader hardcodes PR168's exact `(model_type, feature_group)` as the
one frozen baseline it will ever score. This module scores *two* selected
models side by side, and PR174 explicitly allows the robust experiment to
select a different model family or feature group than PR168 (spec section
7) — so the compatibility checks below verify internal consistency (the
artifact's own recorded feature columns/schema version match what this
codebase expects) without assuming which family or group won.
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


class ArtifactNotFoundError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"required model artifact not found: {path} — generate it via "
            "the models CLI before running a robustness comparison"
        )
        self.path = path


class IncompatibleArtifactError(Exception):
    """Raised when a model artifact does not match this codebase's current
    feature schema/order — never silently tolerated."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise ArtifactNotFoundError(path)


@dataclass(frozen=True)
class ModelArtifacts:
    pipeline: Pipeline
    pipeline_path: Path
    pipeline_sha256: str
    model_metadata: dict[str, Any]
    feature_group: str
    class_order: tuple[str, ...]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "pipeline_path": str(self.pipeline_path),
            "pipeline_sha256": self.pipeline_sha256,
            "model_type": self.model_metadata["model_type"],
            "feature_group": self.feature_group,
            "hyperparameters": self.model_metadata["hyperparameters"],
            "class_order": list(self.class_order),
            "source_dataset_id": self.model_metadata["source_dataset_id"],
            "source_feature_schema_version": (
                self.model_metadata["source_feature_schema_version"]
            ),
        }


def load_model_artifacts(models_directory: Path) -> ModelArtifacts:
    """Load `selected_pipeline.joblib` + `model_metadata.json` from a
    `models` CLI output directory (either the original pilot models
    directory or a robust-training-candidate one)."""
    pipeline_path = models_directory / "artifacts" / "selected_pipeline.joblib"
    model_metadata_path = models_directory / "artifacts" / "model_metadata.json"

    _require_file(pipeline_path)
    _require_file(model_metadata_path)

    model_metadata = json.loads(model_metadata_path.read_text())
    feature_group = model_metadata["feature_group"]
    if feature_group not in FEATURE_GROUPS:
        raise IncompatibleArtifactError(
            f"model_metadata.json's feature_group is {feature_group!r}, not "
            f"one of the known groups {sorted(FEATURE_GROUPS)}"
        )
    if model_metadata["feature_columns"] != FEATURE_GROUPS[feature_group]:
        raise IncompatibleArtifactError(
            "model_metadata.json's feature_columns does not match "
            f"models.feature_groups.FEATURE_GROUPS[{feature_group!r}] — the "
            "model artifact was built against a different feature schema"
        )
    source_schema_version = model_metadata.get("source_feature_schema_version")
    if source_schema_version != FEATURE_SCHEMA_VERSION:
        raise IncompatibleArtifactError(
            f"model_metadata.json's source_feature_schema_version "
            f"({source_schema_version!r}) does not match this codebase's "
            f"features.config.FEATURE_SCHEMA_VERSION ({FEATURE_SCHEMA_VERSION!r})"
        )

    pipeline = joblib.load(pipeline_path)
    if "classifier" not in pipeline.named_steps:
        raise IncompatibleArtifactError(
            "selected_pipeline.joblib has no 'classifier' step — cannot "
            "derive predict_proba's class order"
        )
    class_order = tuple(pipeline.named_steps["classifier"].classes_)

    return ModelArtifacts(
        pipeline=pipeline,
        pipeline_path=pipeline_path,
        pipeline_sha256=_sha256_file(pipeline_path),
        model_metadata=model_metadata,
        feature_group=feature_group,
        class_order=class_order,
    )
