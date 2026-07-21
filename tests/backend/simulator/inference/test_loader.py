"""`load_promoted_fault_system` specifications (spec section 3 / test item
"Artifact loading")."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from backend.simulator.inference.loader import (
    PromotedArtifactMismatchError,
    PromotedArtifactNotFoundError,
    UnexpectedArtifactFileError,
    load_promoted_fault_system,
)

from .conftest import TinyRuntimeFixture


def _copy_bundle(source: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "bundle-copy"
    shutil.copytree(source, destination)
    return destination


def test_valid_bundle_loads(tiny_runtime_fixture: TinyRuntimeFixture) -> None:
    system = load_promoted_fault_system(tiny_runtime_fixture.bundle_dir)
    assert system.feature_group == "D"


def test_missing_pipeline_raises(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    bundle = _copy_bundle(tiny_runtime_fixture.bundle_dir, tmp_path)
    (bundle / "pipeline.joblib").unlink()
    with pytest.raises(PromotedArtifactNotFoundError):
        load_promoted_fault_system(bundle)


def test_missing_policy_raises(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    bundle = _copy_bundle(tiny_runtime_fixture.bundle_dir, tmp_path)
    (bundle / "alert_policy.json").unlink()
    with pytest.raises(PromotedArtifactNotFoundError):
        load_promoted_fault_system(bundle)


def test_missing_metadata_raises(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    bundle = _copy_bundle(tiny_runtime_fixture.bundle_dir, tmp_path)
    (bundle / "system_metadata.json").unlink()
    with pytest.raises(PromotedArtifactNotFoundError):
        load_promoted_fault_system(bundle)


def test_extra_file_rejected(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    bundle = _copy_bundle(tiny_runtime_fixture.bundle_dir, tmp_path)
    (bundle / "extra_file.txt").write_text("not part of the contract")
    with pytest.raises(UnexpectedArtifactFileError):
        load_promoted_fault_system(bundle)


def test_model_hash_mismatch_raises(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    bundle = _copy_bundle(tiny_runtime_fixture.bundle_dir, tmp_path)
    metadata_path = bundle / "system_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["model_hash"] = "0" * 64
    # metadata_hash must still be self-consistent so the model-hash check
    # (not the metadata self-hash check) is the one that fires.
    from backend.simulator.inference.bundle import _canonical_json_hash

    payload = {k: v for k, v in metadata.items() if k != "metadata_hash"}
    metadata["metadata_hash"] = _canonical_json_hash(payload)
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(PromotedArtifactMismatchError, match="model_hash"):
        load_promoted_fault_system(bundle)


def test_policy_hash_mismatch_raises(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    bundle = _copy_bundle(tiny_runtime_fixture.bundle_dir, tmp_path)
    metadata_path = bundle / "system_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["policy_hash"] = "0" * 64
    from backend.simulator.inference.bundle import _canonical_json_hash

    payload = {k: v for k, v in metadata.items() if k != "metadata_hash"}
    metadata["metadata_hash"] = _canonical_json_hash(payload)
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(PromotedArtifactMismatchError, match="policy_hash"):
        load_promoted_fault_system(bundle)


def test_metadata_self_hash_mismatch_raises(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    bundle = _copy_bundle(tiny_runtime_fixture.bundle_dir, tmp_path)
    metadata_path = bundle / "system_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["metadata_hash"] = "0" * 64  # stale, doesn't match recomputed
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(PromotedArtifactMismatchError, match="metadata_hash"):
        load_promoted_fault_system(bundle)


def test_feature_order_mismatch_raises(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    bundle = _copy_bundle(tiny_runtime_fixture.bundle_dir, tmp_path)
    metadata_path = bundle / "system_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["feature_order"] = ["not_a_real_column"]
    from backend.simulator.inference.bundle import _canonical_json_hash

    payload = {k: v for k, v in metadata.items() if k != "metadata_hash"}
    metadata["metadata_hash"] = _canonical_json_hash(payload)
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(PromotedArtifactMismatchError, match="feature_order"):
        load_promoted_fault_system(bundle)


def test_class_order_mismatch_raises(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    bundle = _copy_bundle(tiny_runtime_fixture.bundle_dir, tmp_path)
    metadata_path = bundle / "system_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["class_order"] = ["healthy", "sensor_anomaly"]
    from backend.simulator.inference.bundle import _canonical_json_hash

    payload = {k: v for k, v in metadata.items() if k != "metadata_hash"}
    metadata["metadata_hash"] = _canonical_json_hash(payload)
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(PromotedArtifactMismatchError, match="class_order"):
        load_promoted_fault_system(bundle)


def test_feature_schema_version_mismatch_raises(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    bundle = _copy_bundle(tiny_runtime_fixture.bundle_dir, tmp_path)
    metadata_path = bundle / "system_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["feature_schema_version"] = "0.1"
    from backend.simulator.inference.bundle import _canonical_json_hash

    payload = {k: v for k, v in metadata.items() if k != "metadata_hash"}
    metadata["metadata_hash"] = _canonical_json_hash(payload)
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(
        PromotedArtifactMismatchError, match="feature_schema_version"
    ):
        load_promoted_fault_system(bundle)


def test_safety_policy_version_mismatch_raises(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    bundle = _copy_bundle(tiny_runtime_fixture.bundle_dir, tmp_path)
    metadata_path = bundle / "system_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["safety_policy_version"] = "0.1"
    from backend.simulator.inference.bundle import _canonical_json_hash

    payload = {k: v for k, v in metadata.items() if k != "metadata_hash"}
    metadata["metadata_hash"] = _canonical_json_hash(payload)
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(
        PromotedArtifactMismatchError, match="safety_policy_version"
    ):
        load_promoted_fault_system(bundle)


def test_hyperparameter_mismatch_raises(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    bundle = _copy_bundle(tiny_runtime_fixture.bundle_dir, tmp_path)
    metadata_path = bundle / "system_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["hyperparameters"] = {"C": 999.0}
    from backend.simulator.inference.bundle import _canonical_json_hash

    payload = {k: v for k, v in metadata.items() if k != "metadata_hash"}
    metadata["metadata_hash"] = _canonical_json_hash(payload)
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(PromotedArtifactMismatchError, match="C="):
        load_promoted_fault_system(bundle)


def test_loader_never_calls_pipeline_fit(
    tiny_runtime_fixture: TinyRuntimeFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No-retraining-fallback proof: patching `Pipeline.fit` to raise
    confirms `load_promoted_fault_system` never calls it."""
    from sklearn.pipeline import Pipeline

    def _fail_if_called(self: Pipeline, *args: object, **kwargs: object) -> None:
        raise AssertionError("load_promoted_fault_system must never call Pipeline.fit")

    monkeypatch.setattr(Pipeline, "fit", _fail_if_called)
    system = load_promoted_fault_system(tiny_runtime_fixture.bundle_dir)
    assert system.feature_group == "D"
