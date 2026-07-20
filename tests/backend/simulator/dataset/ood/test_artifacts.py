"""Frozen-artifact compatibility checks (spec section 14, "Artifact
compatibility") — every mismatch must raise, never silently retrain.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from backend.simulator.dataset.ood.artifacts import (
    ArtifactNotFoundError,
    IncompatibleArtifactError,
    load_frozen_artifacts,
)
from tests.backend.simulator.dataset.ood.conftest import TinyFrozenArtifacts


def test_loads_successfully_and_derives_class_order_from_the_pipeline(
    tiny_frozen_artifacts: TinyFrozenArtifacts,
) -> None:
    artifacts = load_frozen_artifacts(
        tiny_frozen_artifacts.models_dir, tiny_frozen_artifacts.alert_policy_dir
    )
    assert artifacts.feature_group == "D"
    assert len(artifacts.class_order) == 4
    assert "healthy" in artifacts.class_order
    assert artifacts.state_machine_config.entry_probability > 0.0
    assert len(artifacts.pipeline_sha256) == 64
    assert len(artifacts.alert_policy_sha256) == 64


def test_missing_pipeline_file_raises(
    tiny_frozen_artifacts: TinyFrozenArtifacts, tmp_path: Path
) -> None:
    empty_models_dir = tmp_path / "empty-models"
    (empty_models_dir / "artifacts").mkdir(parents=True)
    with pytest.raises(ArtifactNotFoundError):
        load_frozen_artifacts(empty_models_dir, tiny_frozen_artifacts.alert_policy_dir)


def test_missing_alert_policy_file_raises(
    tiny_frozen_artifacts: TinyFrozenArtifacts, tmp_path: Path
) -> None:
    empty_alert_policy_dir = tmp_path / "empty-alert-policy"
    (empty_alert_policy_dir / "artifacts").mkdir(parents=True)
    with pytest.raises(ArtifactNotFoundError):
        load_frozen_artifacts(tiny_frozen_artifacts.models_dir, empty_alert_policy_dir)


def _copy_models_dir(source: Path, dest: Path) -> Path:
    shutil.copytree(source, dest)
    return dest


def test_feature_group_mismatch_rejected(
    tiny_frozen_artifacts: TinyFrozenArtifacts, tmp_path: Path
) -> None:
    corrupted = _copy_models_dir(
        tiny_frozen_artifacts.models_dir, tmp_path / "corrupted"
    )
    metadata_path = corrupted / "artifacts" / "model_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["feature_group"] = "A"
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(IncompatibleArtifactError):
        load_frozen_artifacts(corrupted, tiny_frozen_artifacts.alert_policy_dir)


def test_source_feature_schema_version_mismatch_rejected(
    tiny_frozen_artifacts: TinyFrozenArtifacts, tmp_path: Path
) -> None:
    corrupted = _copy_models_dir(
        tiny_frozen_artifacts.models_dir, tmp_path / "corrupted"
    )
    metadata_path = corrupted / "artifacts" / "model_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["source_feature_schema_version"] = "0.1"
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(IncompatibleArtifactError):
        load_frozen_artifacts(corrupted, tiny_frozen_artifacts.alert_policy_dir)


def test_class_order_mismatch_between_pipeline_and_alert_policy_rejected(
    tiny_frozen_artifacts: TinyFrozenArtifacts, tmp_path: Path
) -> None:
    corrupted_policy_dir = tmp_path / "corrupted-alert-policy"
    shutil.copytree(tiny_frozen_artifacts.alert_policy_dir, corrupted_policy_dir)
    policy_path = corrupted_policy_dir / "artifacts" / "alert_policy.json"
    policy = json.loads(policy_path.read_text())
    policy["class_order"] = list(reversed(policy["class_order"]))
    policy_path.write_text(json.dumps(policy))

    with pytest.raises(IncompatibleArtifactError):
        load_frozen_artifacts(tiny_frozen_artifacts.models_dir, corrupted_policy_dir)


def test_malformed_alert_policy_missing_state_machine_config_rejected(
    tiny_frozen_artifacts: TinyFrozenArtifacts, tmp_path: Path
) -> None:
    corrupted_policy_dir = tmp_path / "no-policy-alert-policy"
    shutil.copytree(tiny_frozen_artifacts.alert_policy_dir, corrupted_policy_dir)
    policy_path = corrupted_policy_dir / "artifacts" / "alert_policy.json"
    policy = json.loads(policy_path.read_text())
    policy["state_machine_config"] = None
    policy_path.write_text(json.dumps(policy))

    with pytest.raises(IncompatibleArtifactError):
        load_frozen_artifacts(tiny_frozen_artifacts.models_dir, corrupted_policy_dir)
