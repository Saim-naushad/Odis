"""`load_model_artifacts` specifications."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pytest

from backend.simulator.dataset.models.feature_groups import FEATURE_GROUPS
from backend.simulator.dataset.models.pipelines import (
    build_logistic_regression_pipeline,
)
from backend.simulator.dataset.robustness.artifacts import (
    ArtifactNotFoundError,
    IncompatibleArtifactError,
    load_model_artifacts,
)

_FEATURE_SCHEMA_VERSION = "1.0"


def _write_artifact(
    models_dir: Path,
    *,
    feature_group: str = "D",
    feature_columns: list[str] | None = None,
    source_feature_schema_version: str = _FEATURE_SCHEMA_VERSION,
    write_pipeline: bool = True,
) -> None:
    artifacts_dir = models_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)

    if write_pipeline:
        pipeline = build_logistic_regression_pipeline(0.1)
        columns = feature_columns or FEATURE_GROUPS[feature_group]
        x = np.zeros((8, len(columns)))
        y = np.array(
            ["healthy", "cooling_degradation"] * 4,
        )
        pipeline.fit(x, y)
        joblib.dump(pipeline, artifacts_dir / "selected_pipeline.joblib")

    metadata = {
        "model_type": "logistic_regression",
        "feature_group": feature_group,
        "feature_columns": feature_columns or FEATURE_GROUPS[feature_group],
        "hyperparameters": {"C": 0.1},
        "source_dataset_id": "test-dataset",
        "source_feature_schema_version": source_feature_schema_version,
    }
    (artifacts_dir / "model_metadata.json").write_text(json.dumps(metadata))


def test_loads_a_valid_artifact(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    _write_artifact(models_dir)

    artifacts = load_model_artifacts(models_dir)

    assert artifacts.feature_group == "D"
    assert artifacts.model_metadata["model_type"] == "logistic_regression"
    assert set(artifacts.class_order) == {"healthy", "cooling_degradation"}
    assert len(artifacts.pipeline_sha256) == 64


def test_missing_pipeline_file_raises(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    _write_artifact(models_dir, write_pipeline=False)

    with pytest.raises(ArtifactNotFoundError):
        load_model_artifacts(models_dir)


def test_unknown_feature_group_raises(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    _write_artifact(models_dir, feature_group="Z", feature_columns=["some_column"])

    with pytest.raises(IncompatibleArtifactError, match="not one of the known groups"):
        load_model_artifacts(models_dir)


def test_mismatched_feature_columns_raises(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    _write_artifact(models_dir, feature_group="A", feature_columns=["wrong_column"])

    with pytest.raises(IncompatibleArtifactError, match="feature_columns"):
        load_model_artifacts(models_dir)


def test_mismatched_schema_version_raises(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    _write_artifact(models_dir, source_feature_schema_version="0.9")

    with pytest.raises(
        IncompatibleArtifactError, match="source_feature_schema_version"
    ):
        load_model_artifacts(models_dir)
