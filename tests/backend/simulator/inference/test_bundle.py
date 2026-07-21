"""`bundle.package_promoted_artifact` specifications (spec section 2)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pytest

from backend.simulator.dataset.models.feature_groups import FEATURE_GROUPS
from backend.simulator.inference.bundle import (
    BundleOutputExistsError,
    SourceArtifactMismatchError,
    SourceArtifactNotFoundError,
    package_promoted_artifact,
)
from backend.simulator.inference.loader import load_promoted_fault_system


def _build_source_dir(tmp_path: Path, tiny_pipeline_path: Path) -> Path:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    import shutil

    pipeline_path = source_dir / "promoted_pipeline.joblib"
    shutil.copy2(tiny_pipeline_path, pipeline_path)

    import hashlib

    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    model_hash = _sha256(pipeline_path)
    alert_policy = {
        "class_order": ["cooling_degradation", "healthy"],
        "state_machine_config": {
            "entry_probability": 0.6,
            "entry_persistence": 3,
            "healthy_exit_probability": 0.5,
            "exit_persistence": 2,
        },
    }
    (source_dir / "promoted_alert_policy.json").write_text(json.dumps(alert_policy))
    metadata = {
        "model_hash": model_hash,
        "policy_hash": "irrelevant-not-reverified-by-packaging",
        "numerical_safety_policy_version": "1.0",
        "feature_order": FEATURE_GROUPS["D"],
        "class_order": ["cooling_degradation", "healthy"],
        "model_type": "logistic_regression",
        "feature_group": "D",
        "hyperparameters": {"C": 0.1},
        "training_dataset_manifest_sha256": "0" * 64,
        "training_feature_manifest_sha256": "0" * 64,
        "git_commit": "deadbeef",
        "promotion_decision": {"decision": "PROMOTE ROBUST MODEL AND POLICY"},
    }
    (source_dir / "promoted_system_metadata.json").write_text(json.dumps(metadata))
    return source_dir


@pytest.fixture
def tiny_pipeline_path(tmp_path: Path) -> Path:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    n_features = len(FEATURE_GROUPS["D"])
    pipeline = Pipeline(
        [("scaler", StandardScaler()), ("classifier", LogisticRegression(C=0.1))]
    )
    pipeline.fit(np.zeros((4, n_features)), ["healthy", "cooling_degradation"] * 2)
    path = tmp_path / "pipeline.joblib"
    joblib.dump(pipeline, path)
    return path


def test_package_promoted_artifact_writes_a_valid_bundle(
    tmp_path: Path, tiny_pipeline_path: Path
) -> None:
    source_dir = _build_source_dir(tmp_path, tiny_pipeline_path)
    output_dir = tmp_path / "bundle"

    paths = package_promoted_artifact(
        source_dir, output_dir, training_dataset_id="test-dataset"
    )

    assert paths.pipeline_path.is_file()
    assert paths.alert_policy_path.is_file()
    assert paths.metadata_path.is_file()

    metadata = json.loads(paths.metadata_path.read_text())
    assert metadata["training_dataset_id"] == "test-dataset"
    assert metadata["system_version"] == "plant_alpha_fault_v1"
    assert "metadata_hash" in metadata


def test_packaged_bundle_loads_through_the_real_loader(
    tmp_path: Path, tiny_pipeline_path: Path
) -> None:
    source_dir = _build_source_dir(tmp_path, tiny_pipeline_path)
    output_dir = tmp_path / "bundle"
    package_promoted_artifact(
        source_dir, output_dir, training_dataset_id="test-dataset"
    )

    system = load_promoted_fault_system(output_dir)
    assert system.training_dataset_id == "test-dataset"


def test_missing_source_pipeline_raises(
    tmp_path: Path, tiny_pipeline_path: Path
) -> None:
    source_dir = _build_source_dir(tmp_path, tiny_pipeline_path)
    (source_dir / "promoted_pipeline.joblib").unlink()

    with pytest.raises(SourceArtifactNotFoundError):
        package_promoted_artifact(
            source_dir, tmp_path / "bundle", training_dataset_id="test-dataset"
        )


def test_source_model_hash_mismatch_raises(
    tmp_path: Path, tiny_pipeline_path: Path
) -> None:
    source_dir = _build_source_dir(tmp_path, tiny_pipeline_path)
    metadata_path = source_dir / "promoted_system_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["model_hash"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(SourceArtifactMismatchError):
        package_promoted_artifact(
            source_dir, tmp_path / "bundle", training_dataset_id="test-dataset"
        )


def test_existing_output_requires_overwrite(
    tmp_path: Path, tiny_pipeline_path: Path
) -> None:
    source_dir = _build_source_dir(tmp_path, tiny_pipeline_path)
    output_dir = tmp_path / "bundle"
    package_promoted_artifact(
        source_dir, output_dir, training_dataset_id="test-dataset"
    )

    with pytest.raises(BundleOutputExistsError):
        package_promoted_artifact(
            source_dir, output_dir, training_dataset_id="test-dataset"
        )

    # overwrite=True succeeds.
    package_promoted_artifact(
        source_dir, output_dir, training_dataset_id="test-dataset", overwrite=True
    )
