"""Offline/online feature and prediction parity (PR176 spec section 6 —
"the most important requirement", and section 12's "Offline/online
parity" test list).

For every sequence below, the runtime session's feature vector, model
probabilities, and diagnosed class at each eligible timestamp are
compared directly against the corresponding offline `features.parquet`
row and the same pipeline's own `predict_proba` on that row — not
approximately, but exactly (floating-point equality, since both paths run
the identical formulas over identical inputs; see `features.row.
compute_feature_row`'s module docstring).
"""

from __future__ import annotations

import numpy as np
import pyarrow.parquet as pq
import pytest

from backend.simulator.inference.result import InferenceStatus
from backend.simulator.inference.session import FaultInferenceSession
from backend.simulator.inference.telemetry import TelemetrySample
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType

from .conftest import TinyRuntimeFixture

_ASSET_ID = "fuel-cell-stack-01"


def _run_ids_by_class(dataset_dir) -> dict[str, str]:  # type: ignore[no-untyped-def]
    runs = pq.read_table(
        dataset_dir / "runs.parquet", columns=["simulation_run_id", "class_label"]
    ).to_pylist()
    by_class: dict[str, str] = {}
    for row in runs:
        by_class.setdefault(row["class_label"], row["simulation_run_id"])
    return by_class


def _observations_for_run(  # type: ignore[no-untyped-def]
    telemetry_table, run_id: str
) -> list[tuple[Observation, ...]]:
    rows = telemetry_table.to_pylist()
    by_elapsed: dict[float, list] = {}
    for row in rows:
        if row["simulation_run_id"] != run_id or row["asset_id"] != _ASSET_ID:
            continue
        by_elapsed.setdefault(row["elapsed_sim_seconds"], []).append(row)

    batches = []
    for elapsed in sorted(by_elapsed):
        observations = tuple(
            Observation(
                id=f"parity-{run_id}-{row['measurement_type']}-{elapsed}",
                asset_id=_ASSET_ID,
                timestamp=row["timestamp"],
                measurement_type=MeasurementType(name=row["measurement_type"]),
                value=row["value"],
                unit=row["unit"],
            )
            for row in by_elapsed[elapsed]
        )
        batches.append(observations)
    return batches


def _offline_features_by_timestamp(features_dir, run_id: str) -> dict:  # type: ignore[no-untyped-def]
    rows = pq.read_table(features_dir / "features.parquet").to_pylist()
    return {
        row["timestamp"]: row
        for row in rows
        if row["simulation_run_id"] == run_id and row["asset_id"] == _ASSET_ID
    }


@pytest.mark.parametrize(
    "class_label",
    [
        "normal_operation",
        "cooling_degradation",
        "hydrogen_supply_issue",
        "sensor_anomaly",
    ],
)
def test_runtime_matches_offline_for_every_class(
    tiny_runtime_fixture: TinyRuntimeFixture, class_label: str
) -> None:
    dataset_dir = tiny_runtime_fixture.dataset_dir
    features_dir = tiny_runtime_fixture.features_dir
    system = tiny_runtime_fixture.system

    run_id = _run_ids_by_class(dataset_dir)[class_label]
    telemetry_table = pq.read_table(dataset_dir / "telemetry.parquet")
    batches = _observations_for_run(telemetry_table, run_id)
    offline_by_timestamp = _offline_features_by_timestamp(features_dir, run_id)

    session = FaultInferenceSession(asset_id=_ASSET_ID, system=system)
    checked_valid_rows = 0
    for observations in batches:
        sample = TelemetrySample.from_observations(observations)
        result = session.ingest(sample)

        if result.status is InferenceStatus.WARMING_UP:
            assert sample.timestamp not in offline_by_timestamp
            continue

        offline_row = offline_by_timestamp.get(sample.timestamp)
        if result.status is InferenceStatus.INSUFFICIENT_DATA:
            assert offline_row is None
            continue

        assert offline_row is not None, (
            f"runtime produced a valid_prediction at {sample.timestamp} but "
            "offline features.parquet has no row there"
        )

        # Exact feature vector, in the pipeline's own required column order.
        offline_vector = np.array(
            [[offline_row[name] for name in system.feature_order]]
        )
        offline_proba = system.pipeline.predict_proba(offline_vector)[0]
        offline_diagnosis = system.class_order[int(np.argmax(offline_proba))]

        assert result.diagnosed_class == offline_diagnosis
        assert result.class_probabilities is not None
        for cls, proba in result.class_probabilities.items():
            offline_p = float(
                offline_proba[system.class_order.index(cls)]
            )
            assert proba == pytest.approx(offline_p, abs=1e-9)
        checked_valid_rows += 1

    assert checked_valid_rows > 0


def test_runtime_matches_offline_rejection_on_near_zero_denominator(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    """A directly forced near-zero `fuel_flow` sample must be reported as
    `insufficient_data` with the same reason offline's safety contract
    would use — proves the PR173 rejection contract, not just the happy
    path, matches exactly at runtime."""
    from backend.simulator.dataset.features.safety import MIN_ABS_FUEL_FLOW_SLPM

    dataset_dir = tiny_runtime_fixture.dataset_dir
    run_id = _run_ids_by_class(dataset_dir)["normal_operation"]
    telemetry_table = pq.read_table(dataset_dir / "telemetry.parquet")
    batches = _observations_for_run(telemetry_table, run_id)

    session = FaultInferenceSession(
        asset_id=_ASSET_ID, system=tiny_runtime_fixture.system
    )
    results = []
    for index, observations in enumerate(batches[:13]):
        if index == 12:
            # Force fuel_flow below its safety floor on the first eligible row.
            observations = tuple(
                obs
                if obs.measurement_type.name != "fuel_flow"
                else Observation(
                    id=obs.id,
                    asset_id=obs.asset_id,
                    timestamp=obs.timestamp,
                    measurement_type=obs.measurement_type,
                    value=MIN_ABS_FUEL_FLOW_SLPM / 2,
                    unit=obs.unit,
                )
                for obs in observations
            )
        sample = TelemetrySample.from_observations(observations)
        results.append(session.ingest(sample))

    last = results[-1]
    assert last.status is InferenceStatus.INSUFFICIENT_DATA
    assert "near_zero_denominator" in last.reason_codes
    assert "power_per_fuel_flow" in last.invalid_feature_names
    assert last.diagnosed_class is None
