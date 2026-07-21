"""`load_frozen_candidate` specifications (spec section 1 / test item
"Frozen candidate loading")."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pytest

from backend.simulator.dataset.features.config import FEATURE_SCHEMA_VERSION
from backend.simulator.dataset.models.feature_groups import FEATURE_GROUPS
from backend.simulator.dataset.models.pipelines import (
    build_logistic_regression_pipeline,
)
from backend.simulator.dataset.robustness.candidate import (
    CandidateArtifactMismatchError,
    CandidateArtifactNotFoundError,
    load_frozen_candidate,
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_pipeline(path: Path, *, feature_group: str = "D") -> None:
    pipeline = build_logistic_regression_pipeline(0.1)
    columns = FEATURE_GROUPS[feature_group]
    x = np.zeros((8, len(columns)))
    y = np.array(["healthy", "cooling_degradation"] * 4)
    pipeline.fit(x, y)
    joblib.dump(pipeline, path)


def _fitted_class_order(pipeline_path: Path) -> list[str]:
    pipeline = joblib.load(pipeline_path)
    return list(pipeline.named_steps["classifier"].classes_)


def _build_valid_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Builds a self-consistent comparison_dir/dataset_dir/features_dir
    triple that `load_frozen_candidate` should accept without error."""
    comparison_dir = tmp_path / "comparison"
    dataset_dir = tmp_path / "dataset"
    features_dir = tmp_path / "features"
    comparison_dir.mkdir()
    dataset_dir.mkdir()
    features_dir.mkdir()

    pipeline_path = comparison_dir / "robust_candidate_pipeline.joblib"
    _write_pipeline(pipeline_path)
    pipeline_sha256 = _sha256_file(pipeline_path)
    class_order = _fitted_class_order(pipeline_path)

    dataset_manifest_path = dataset_dir / "dataset_manifest.json"
    dataset_manifest_path.write_text(json.dumps({"dataset_id": "robust-fixture"}))
    dataset_manifest_sha256 = _sha256_file(dataset_manifest_path)

    feature_manifest_path = features_dir / "feature_manifest.json"
    feature_manifest_path.write_text(json.dumps({"feature_schema_version": "1.0"}))
    feature_manifest_sha256 = _sha256_file(feature_manifest_path)

    metadata = {
        "model_type": "logistic_regression",
        "feature_group": "D",
        "hyperparameters": {"C": 0.1},
        "class_order": class_order,
        "source_dataset_id": "robust-fixture",
        "source_feature_schema_version": FEATURE_SCHEMA_VERSION,
        "pipeline_sha256": pipeline_sha256,
    }
    (comparison_dir / "robust_candidate_metadata.json").write_text(
        json.dumps(metadata)
    )

    summary = {
        "training_dataset_manifest_sha256": dataset_manifest_sha256,
        "training_feature_manifest_sha256": feature_manifest_sha256,
        "feature_order": FEATURE_GROUPS["D"],
        "class_order": class_order,
        "pr173_safety_policy_version": FEATURE_SCHEMA_VERSION,
    }
    (comparison_dir / "robust_training_summary.json").write_text(
        json.dumps(summary)
    )

    return comparison_dir, dataset_dir, features_dir


def test_loads_a_valid_candidate(tmp_path: Path) -> None:
    comparison_dir, dataset_dir, features_dir = _build_valid_fixture(tmp_path)

    candidate = load_frozen_candidate(
        comparison_dir,
        training_dataset_dir=dataset_dir,
        training_features_dir=features_dir,
    )

    assert candidate.feature_group == "D"
    assert set(candidate.class_order) == {"healthy", "cooling_degradation"}
    assert len(candidate.pipeline_sha256) == 64


def test_missing_pipeline_raises_not_found(tmp_path: Path) -> None:
    comparison_dir, dataset_dir, features_dir = _build_valid_fixture(tmp_path)
    (comparison_dir / "robust_candidate_pipeline.joblib").unlink()

    with pytest.raises(CandidateArtifactNotFoundError):
        load_frozen_candidate(
            comparison_dir,
            training_dataset_dir=dataset_dir,
            training_features_dir=features_dir,
        )


def test_missing_metadata_raises_not_found(tmp_path: Path) -> None:
    comparison_dir, dataset_dir, features_dir = _build_valid_fixture(tmp_path)
    (comparison_dir / "robust_candidate_metadata.json").unlink()

    with pytest.raises(CandidateArtifactNotFoundError):
        load_frozen_candidate(
            comparison_dir,
            training_dataset_dir=dataset_dir,
            training_features_dir=features_dir,
        )


def test_model_hash_mismatch_raises(tmp_path: Path) -> None:
    comparison_dir, dataset_dir, features_dir = _build_valid_fixture(tmp_path)
    metadata_path = comparison_dir / "robust_candidate_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["pipeline_sha256"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(CandidateArtifactMismatchError, match="sha256"):
        load_frozen_candidate(
            comparison_dir,
            training_dataset_dir=dataset_dir,
            training_features_dir=features_dir,
        )


def test_training_dataset_hash_mismatch_raises(tmp_path: Path) -> None:
    comparison_dir, dataset_dir, features_dir = _build_valid_fixture(tmp_path)
    # Mutate the dataset manifest on disk after the summary recorded its hash.
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps({"dataset_id": "changed-since-freeze"})
    )

    with pytest.raises(CandidateArtifactMismatchError, match="dataset_manifest"):
        load_frozen_candidate(
            comparison_dir,
            training_dataset_dir=dataset_dir,
            training_features_dir=features_dir,
        )


def test_feature_manifest_hash_mismatch_raises(tmp_path: Path) -> None:
    comparison_dir, dataset_dir, features_dir = _build_valid_fixture(tmp_path)
    (features_dir / "feature_manifest.json").write_text(
        json.dumps({"feature_schema_version": "1.0", "changed": True})
    )

    with pytest.raises(CandidateArtifactMismatchError, match="feature_manifest"):
        load_frozen_candidate(
            comparison_dir,
            training_dataset_dir=dataset_dir,
            training_features_dir=features_dir,
        )


def test_feature_order_mismatch_raises(tmp_path: Path) -> None:
    comparison_dir, dataset_dir, features_dir = _build_valid_fixture(tmp_path)
    summary_path = comparison_dir / "robust_training_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["feature_order"] = ["not_a_real_column"]
    summary_path.write_text(json.dumps(summary))

    with pytest.raises(CandidateArtifactMismatchError, match="feature_order"):
        load_frozen_candidate(
            comparison_dir,
            training_dataset_dir=dataset_dir,
            training_features_dir=features_dir,
        )


def test_class_order_mismatch_raises(tmp_path: Path) -> None:
    comparison_dir, dataset_dir, features_dir = _build_valid_fixture(tmp_path)
    metadata_path = comparison_dir / "robust_candidate_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["class_order"] = ["healthy", "sensor_anomaly"]
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(CandidateArtifactMismatchError, match="class_order"):
        load_frozen_candidate(
            comparison_dir,
            training_dataset_dir=dataset_dir,
            training_features_dir=features_dir,
        )


def test_schema_version_mismatch_raises(tmp_path: Path) -> None:
    comparison_dir, dataset_dir, features_dir = _build_valid_fixture(tmp_path)
    metadata_path = comparison_dir / "robust_candidate_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["source_feature_schema_version"] = "0.1"
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(
        CandidateArtifactMismatchError, match="source_feature_schema_version"
    ):
        load_frozen_candidate(
            comparison_dir,
            training_dataset_dir=dataset_dir,
            training_features_dir=features_dir,
        )


def test_load_frozen_candidate_never_fits_a_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No-retraining-fallback: patching `Pipeline.fit` to raise proves
    `load_frozen_candidate` never calls it — only `joblib.load`."""
    comparison_dir, dataset_dir, features_dir = _build_valid_fixture(tmp_path)

    from sklearn.pipeline import Pipeline

    def _fail_if_called(self: Pipeline, *args: object, **kwargs: object) -> None:
        raise AssertionError("load_frozen_candidate must never call Pipeline.fit")

    monkeypatch.setattr(Pipeline, "fit", _fail_if_called)

    candidate = load_frozen_candidate(
        comparison_dir,
        training_dataset_dir=dataset_dir,
        training_features_dir=features_dir,
    )
    assert candidate.feature_group == "D"
