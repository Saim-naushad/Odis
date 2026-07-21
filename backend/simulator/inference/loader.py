"""Strict promoted-system loader (PR176 spec section 3).

`load_promoted_fault_system` is the one place a runtime caller ever loads
the PR175-promoted model+policy — it never refits, never regenerates a
missing file, and never silently substitutes a default. Every check
raises a specific, named exception with an operator-actionable message.
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
from backend.simulator.inference.bundle import BUNDLE_FILENAMES, _canonical_json_hash


class PromotedArtifactNotFoundError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"required runtime artifact not found: {path} — package a bundle "
            "via backend.simulator.inference.bundle.package_promoted_artifact "
            "before loading (this loader never trains or regenerates a "
            "fallback)"
        )
        self.path = path


class UnexpectedArtifactFileError(Exception):
    def __init__(self, bundle_dir: Path, unexpected: list[str]) -> None:
        super().__init__(
            f"{bundle_dir} contains unexpected file(s) not part of the "
            f"runtime bundle contract: {sorted(unexpected)} (expected exactly "
            f"{sorted(BUNDLE_FILENAMES)})"
        )
        self.unexpected = unexpected


class PromotedArtifactMismatchError(Exception):
    """Raised for any hash, order, version, or estimator-configuration
    mismatch — never silently tolerated."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PromotedFaultSystem:
    """The complete, verified, immutable-in-practice promoted system.

    `pipeline`/`alert_policy_config` are the only objects runtime code
    calls; every other field is provenance recorded for logging/evidence
    and reproducibility, never mutated after loading.
    """

    pipeline: Pipeline
    feature_group: str
    feature_order: tuple[str, ...]
    class_order: tuple[str, ...]
    alert_policy_config: StateMachineConfig
    system_version: str
    model_hash: str
    policy_hash: str
    metadata_hash: str
    feature_schema_version: str
    safety_policy_version: str
    training_dataset_id: str
    metadata: dict[str, Any]


def load_promoted_fault_system(bundle_dir: Path) -> PromotedFaultSystem:
    """Load and fully verify a runtime bundle written by
    `bundle.package_promoted_artifact` — see that module's docstring for
    the bundle's on-disk shape.
    """
    if not bundle_dir.is_dir():
        raise PromotedArtifactNotFoundError(bundle_dir)

    actual_files = {p.name for p in bundle_dir.iterdir() if p.is_file()}
    expected_files = set(BUNDLE_FILENAMES)
    missing = expected_files - actual_files
    if missing:
        raise PromotedArtifactNotFoundError(bundle_dir / sorted(missing)[0])
    unexpected = actual_files - expected_files
    if unexpected:
        raise UnexpectedArtifactFileError(bundle_dir, sorted(unexpected))

    pipeline_path = bundle_dir / "pipeline.joblib"
    alert_policy_path = bundle_dir / "alert_policy.json"
    metadata_path = bundle_dir / "system_metadata.json"

    metadata = json.loads(metadata_path.read_text())

    # --- metadata self-hash --------------------------------------------
    recorded_metadata_hash = metadata.get("metadata_hash")
    payload_without_hash = {k: v for k, v in metadata.items() if k != "metadata_hash"}
    recomputed_metadata_hash = _canonical_json_hash(payload_without_hash)
    if recomputed_metadata_hash != recorded_metadata_hash:
        raise PromotedArtifactMismatchError(
            f"{metadata_path}'s own content does not match its recorded "
            f"metadata_hash ({recorded_metadata_hash!r} != recomputed "
            f"{recomputed_metadata_hash!r}) — the metadata file may have been "
            "edited after packaging"
        )

    # --- model hash -------------------------------------------------------
    actual_model_hash = _sha256_file(pipeline_path)
    if actual_model_hash != metadata.get("model_hash"):
        raise PromotedArtifactMismatchError(
            f"{pipeline_path}'s sha256 ({actual_model_hash}) does not match "
            f"system_metadata.json's recorded model_hash "
            f"({metadata.get('model_hash')})"
        )

    # --- policy hash --------------------------------------------------------
    actual_policy_hash = _sha256_file(alert_policy_path)
    if actual_policy_hash != metadata.get("policy_hash"):
        raise PromotedArtifactMismatchError(
            f"{alert_policy_path}'s sha256 ({actual_policy_hash}) does not "
            f"match system_metadata.json's recorded policy_hash "
            f"({metadata.get('policy_hash')})"
        )

    # --- feature order / schema version / safety-policy version -----------
    feature_group = metadata["feature_group"]
    if feature_group not in FEATURE_GROUPS:
        raise PromotedArtifactMismatchError(
            f"system_metadata.json's feature_group is {feature_group!r}, not "
            f"one of the known groups {sorted(FEATURE_GROUPS)}"
        )
    feature_order = tuple(metadata.get("feature_order", []))
    if list(feature_order) != FEATURE_GROUPS[feature_group]:
        raise PromotedArtifactMismatchError(
            "system_metadata.json's feature_order does not match "
            f"models.feature_groups.FEATURE_GROUPS[{feature_group!r}]"
        )
    feature_schema_version = metadata.get("feature_schema_version")
    if feature_schema_version != FEATURE_SCHEMA_VERSION:
        raise PromotedArtifactMismatchError(
            f"system_metadata.json's feature_schema_version "
            f"({feature_schema_version!r}) does not match this codebase's "
            f"features.config.FEATURE_SCHEMA_VERSION ({FEATURE_SCHEMA_VERSION!r})"
        )
    safety_policy_version = metadata.get("safety_policy_version")
    if safety_policy_version != FEATURE_SCHEMA_VERSION:
        raise PromotedArtifactMismatchError(
            f"system_metadata.json's safety_policy_version "
            f"({safety_policy_version!r}) does not match this codebase's "
            f"features.config.FEATURE_SCHEMA_VERSION ({FEATURE_SCHEMA_VERSION!r})"
        )

    # --- pipeline load, class order, estimator type/configuration ---------
    pipeline = joblib.load(pipeline_path)
    if "classifier" not in pipeline.named_steps:
        raise PromotedArtifactMismatchError(
            "pipeline.joblib has no 'classifier' step — cannot verify "
            "estimator type or derive predict_proba's class order"
        )
    classifier = pipeline.named_steps["classifier"]
    class_order = tuple(classifier.classes_)
    recorded_class_order = tuple(metadata.get("class_order", []))
    if class_order != recorded_class_order:
        raise PromotedArtifactMismatchError(
            f"pipeline.joblib's fitted class order {class_order} does not "
            f"match system_metadata.json's recorded class_order "
            f"{recorded_class_order}"
        )

    expected_model_type = metadata["model_type"]
    actual_model_type = _sklearn_model_type_name(classifier)
    if actual_model_type != expected_model_type:
        raise PromotedArtifactMismatchError(
            f"pipeline.joblib's classifier type ({actual_model_type!r}) does "
            f"not match system_metadata.json's recorded model_type "
            f"({expected_model_type!r})"
        )
    _verify_hyperparameters(
        classifier, expected=metadata.get("hyperparameters", {})
    )

    alert_policy = json.loads(alert_policy_path.read_text())
    alert_policy_class_order = tuple(alert_policy.get("class_order", []))
    if alert_policy_class_order != class_order:
        raise PromotedArtifactMismatchError(
            f"alert_policy.json's class_order {alert_policy_class_order} does "
            f"not match pipeline.joblib's fitted class order {class_order}"
        )
    state_machine_config_data = alert_policy.get("state_machine_config")
    if state_machine_config_data is None:
        raise PromotedArtifactMismatchError(
            "alert_policy.json has no state_machine_config"
        )
    alert_policy_config = StateMachineConfig(
        entry_probability=float(state_machine_config_data["entry_probability"]),
        entry_persistence=int(state_machine_config_data["entry_persistence"]),
        healthy_exit_probability=float(
            state_machine_config_data["healthy_exit_probability"]
        ),
        exit_persistence=int(state_machine_config_data["exit_persistence"]),
    )

    return PromotedFaultSystem(
        pipeline=pipeline,
        feature_group=feature_group,
        feature_order=feature_order,
        class_order=class_order,
        alert_policy_config=alert_policy_config,
        system_version=metadata.get("system_version", "unknown"),
        model_hash=actual_model_hash,
        policy_hash=actual_policy_hash,
        metadata_hash=recomputed_metadata_hash,
        feature_schema_version=feature_schema_version,
        safety_policy_version=safety_policy_version,
        training_dataset_id=metadata.get("training_dataset_id", "unknown"),
        metadata=metadata,
    )


_MODEL_TYPE_NAMES: dict[str, str] = {
    "LogisticRegression": "logistic_regression",
    "HistGradientBoostingClassifier": "histogram_gradient_boosting",
}


def _sklearn_model_type_name(classifier: object) -> str:
    class_name = type(classifier).__name__
    return _MODEL_TYPE_NAMES.get(class_name, class_name)


def _verify_hyperparameters(classifier: object, *, expected: dict[str, Any]) -> None:
    """Only re-checks the hyperparameters this codebase's own training
    search actually varies (`C` for logistic regression) — a full
    `get_params()` diff would also flag sklearn's own unrelated defaults
    changing between library versions, which is not what this check is
    for."""
    if "C" in expected:
        actual_c = getattr(classifier, "C", None)
        if actual_c != expected["C"]:
            raise PromotedArtifactMismatchError(
                f"pipeline.joblib's classifier has C={actual_c!r}, expected "
                f"{expected['C']!r} per system_metadata.json's hyperparameters"
            )
