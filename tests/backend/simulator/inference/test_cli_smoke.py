"""CLI smoke tests (spec section 11 / test item "CLI smoke")."""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq

from backend.simulator.inference.__main__ import main as replay_main
from backend.simulator.inference.bundle_cli import main as bundle_cli_main

from .conftest import TinyRuntimeFixture


def _run_id_for_class(dataset_dir: Path, class_label: str) -> str:
    runs = pq.read_table(
        dataset_dir / "runs.parquet", columns=["simulation_run_id", "class_label"]
    ).to_pylist()
    return str(
        next(r["simulation_run_id"] for r in runs if r["class_label"] == class_label)
    )


def test_replay_cli_smoke_succeeds(
    tiny_runtime_fixture: TinyRuntimeFixture, capsys: object
) -> None:
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "cooling_degradation")
    exit_code = replay_main(
        [
            "--artifact-dir",
            str(tiny_runtime_fixture.bundle_dir),
            "--telemetry",
            str(tiny_runtime_fixture.dataset_dir / "telemetry.parquet"),
            "--run-id",
            run_id,
            "--asset-id",
            "fuel-cell-stack-01",
        ]
    )
    assert exit_code == 0


def test_replay_cli_reports_missing_artifact_clearly(
    tiny_runtime_fixture: TinyRuntimeFixture, tmp_path: Path
) -> None:
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    exit_code = replay_main(
        [
            "--artifact-dir",
            str(tmp_path / "does-not-exist"),
            "--telemetry",
            str(tiny_runtime_fixture.dataset_dir / "telemetry.parquet"),
            "--run-id",
            run_id,
            "--asset-id",
            "fuel-cell-stack-01",
        ]
    )
    assert exit_code == 1


def test_replay_cli_reports_unknown_run_clearly(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    exit_code = replay_main(
        [
            "--artifact-dir",
            str(tiny_runtime_fixture.bundle_dir),
            "--telemetry",
            str(tiny_runtime_fixture.dataset_dir / "telemetry.parquet"),
            "--run-id",
            "not-a-real-run",
            "--asset-id",
            "fuel-cell-stack-01",
        ]
    )
    assert exit_code == 1


def test_bundle_cli_smoke(tmp_path: Path) -> None:
    """The packaging CLI, exercised against a tiny hand-built source dir
    (mirrors `test_bundle.py`'s own fixture shape)."""
    import hashlib
    import json

    import joblib
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    from backend.simulator.dataset.models.feature_groups import FEATURE_GROUPS

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    n_features = len(FEATURE_GROUPS["D"])
    pipeline = Pipeline(
        [("scaler", StandardScaler()), ("classifier", LogisticRegression(C=0.1))]
    )
    pipeline.fit(np.zeros((4, n_features)), ["healthy", "cooling_degradation"] * 2)
    pipeline_path = source_dir / "promoted_pipeline.joblib"
    joblib.dump(pipeline, pipeline_path)
    model_hash = hashlib.sha256(pipeline_path.read_bytes()).hexdigest()

    (source_dir / "promoted_alert_policy.json").write_text(
        json.dumps(
            {
                "class_order": ["cooling_degradation", "healthy"],
                "state_machine_config": {
                    "entry_probability": 0.6,
                    "entry_persistence": 3,
                    "healthy_exit_probability": 0.5,
                    "exit_persistence": 2,
                },
            }
        )
    )
    (source_dir / "promoted_system_metadata.json").write_text(
        json.dumps(
            {
                "model_hash": model_hash,
                "policy_hash": "unused",
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
        )
    )

    exit_code = bundle_cli_main(
        [
            "--source",
            str(source_dir),
            "--output",
            str(tmp_path / "bundle"),
            "--training-dataset-id",
            "smoke-test-dataset",
        ]
    )
    assert exit_code == 0
    assert (tmp_path / "bundle" / "pipeline.joblib").is_file()


def test_bundle_cli_reports_missing_source_clearly(tmp_path: Path) -> None:
    exit_code = bundle_cli_main(
        [
            "--source",
            str(tmp_path / "does-not-exist"),
            "--output",
            str(tmp_path / "bundle"),
            "--training-dataset-id",
            "smoke-test-dataset",
        ]
    )
    assert exit_code == 1
