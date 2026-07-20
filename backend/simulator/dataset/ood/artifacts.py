"""Loads the frozen PR168 model pipeline and PR170 alert policy for OOD
evaluation (spec section 7).

Every check here fails loudly and specifically rather than silently
retraining or falling back to a refit — this module's entire purpose is
to guarantee the evaluation scores the *exact* artifacts already selected,
never a fresh fit on whatever data happens to be at hand.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
from sklearn.pipeline import Pipeline

from backend.simulator.dataset.alert_policy.state_machine import StateMachineConfig
from backend.simulator.dataset.features.config import FEATURE_SCHEMA_VERSION
from backend.simulator.dataset.models.feature_groups import FEATURE_GROUPS
from backend.simulator.dataset.models.selected_baseline import (
    BASE_FEATURE_GROUP,
    BASE_MODEL_TYPE,
)


class ArtifactNotFoundError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"required frozen artifact not found: {path} — generate it via "
            "the models/alert_policy CLIs before running OOD evaluation "
            "(this module never trains a fallback)"
        )
        self.path = path


class IncompatibleArtifactError(Exception):
    """Raised for any mismatch between the frozen artifacts and the policy
    this evaluation is scoped to freeze (spec section 1) — never silently
    tolerated."""


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
class FrozenArtifacts:
    pipeline: Pipeline
    pipeline_path: Path
    pipeline_sha256: str
    model_metadata: dict[str, Any]
    feature_group: str
    class_order: tuple[str, ...]
    alert_policy: dict[str, Any]
    alert_policy_path: Path
    alert_policy_sha256: str
    state_machine_config: StateMachineConfig

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
            "alert_policy_path": str(self.alert_policy_path),
            "alert_policy_sha256": self.alert_policy_sha256,
            "state_machine_config": self.state_machine_config.to_json_dict(),
        }


def load_frozen_artifacts(
    models_directory: Path, alert_policy_directory: Path
) -> FrozenArtifacts:
    """Load PR168's `selected_pipeline.joblib` + `model_metadata.json` and
    PR170's `alert_policy.json`, verifying every compatibility invariant
    this evaluation depends on. Raises rather than falls back whenever an
    invariant does not hold.
    """
    pipeline_path = models_directory / "artifacts" / "selected_pipeline.joblib"
    model_metadata_path = models_directory / "artifacts" / "model_metadata.json"
    alert_policy_path = alert_policy_directory / "artifacts" / "alert_policy.json"

    _require_file(pipeline_path)
    _require_file(model_metadata_path)
    _require_file(alert_policy_path)

    model_metadata = json.loads(model_metadata_path.read_text())
    if model_metadata["model_type"] != BASE_MODEL_TYPE:
        raise IncompatibleArtifactError(
            f"model_metadata.json's model_type is {model_metadata['model_type']!r}, "
            f"expected the frozen selected baseline {BASE_MODEL_TYPE!r}"
        )
    feature_group = model_metadata["feature_group"]
    if feature_group != BASE_FEATURE_GROUP:
        raise IncompatibleArtifactError(
            f"model_metadata.json's feature_group is {feature_group!r}, expected "
            f"the frozen selected baseline {BASE_FEATURE_GROUP!r}"
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

    alert_policy = json.loads(alert_policy_path.read_text())
    alert_policy_class_order = tuple(alert_policy["class_order"])
    if alert_policy_class_order != class_order:
        raise IncompatibleArtifactError(
            f"alert_policy.json's class_order {alert_policy_class_order} does "
            f"not match selected_pipeline.joblib's fitted class order "
            f"{class_order} — these two artifacts were not produced from the "
            "same training run"
        )
    state_machine_config_data = alert_policy.get("state_machine_config")
    if state_machine_config_data is None:
        raise IncompatibleArtifactError(
            "alert_policy.json has no state_machine_config (no policy was "
            "selected) — OOD alert evaluation requires a frozen policy"
        )
    state_machine_config = StateMachineConfig(
        entry_probability=float(state_machine_config_data["entry_probability"]),
        entry_persistence=int(state_machine_config_data["entry_persistence"]),
        healthy_exit_probability=float(
            state_machine_config_data["healthy_exit_probability"]
        ),
        exit_persistence=int(state_machine_config_data["exit_persistence"]),
    )

    return FrozenArtifacts(
        pipeline=pipeline,
        pipeline_path=pipeline_path,
        pipeline_sha256=_sha256_file(pipeline_path),
        model_metadata=model_metadata,
        feature_group=feature_group,
        class_order=class_order,
        alert_policy=alert_policy,
        alert_policy_path=alert_policy_path,
        alert_policy_sha256=_sha256_file(alert_policy_path),
        state_machine_config=state_machine_config,
    )
