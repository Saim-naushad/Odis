"""Label-construction correctness (PR167 spec sections 8 and 12)."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.simulator.dataset.features.labels import build_label_rows, derive_label


def test_inactive_row_is_healthy_regardless_of_fault_type() -> None:
    # A row can carry a non-"none" fault_type while inactive (before/after
    # the fault window) — ground_truth.py's own documented behavior.
    assert (
        derive_label(
            fault_active=False,
            fault_type="cooling_degradation",
            sensor_corruption_type="none",
        )
        == "healthy"
    )


def test_active_cooling_degradation_maps_directly() -> None:
    assert (
        derive_label(
            fault_active=True,
            fault_type="cooling_degradation",
            sensor_corruption_type="none",
        )
        == "cooling_degradation"
    )


def test_active_hydrogen_supply_issue_maps_directly() -> None:
    assert (
        derive_label(
            fault_active=True,
            fault_type="hydrogen_supply_issue",
            sensor_corruption_type="none",
        )
        == "hydrogen_supply_issue"
    )


def test_active_sensor_anomaly_maps_from_sensor_corruption_type() -> None:
    assert (
        derive_label(
            fault_active=True, fault_type="none", sensor_corruption_type="bias"
        )
        == "sensor_anomaly"
    )


def test_non_target_asset_row_is_healthy() -> None:
    # Ground truth already reports non-target assets as fault_active=False
    # with fault_type="none"/sensor_corruption_type="none" (PR161's
    # single-target-per-run invariant) — derive_label needs no special case.
    assert (
        derive_label(
            fault_active=False, fault_type="none", sensor_corruption_type="none"
        )
        == "healthy"
    )


def test_build_label_rows_never_uses_configured_run_class() -> None:
    """The run's configured `class_label` (a fault class) must not leak
    into inactive rows' derived label — this is the crucial distinction
    the spec calls out."""
    ground_truth_rows = [
        {
            "simulation_run_id": "run-a",
            "asset_id": "asset-1",
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            "fault_active": False,
            "fault_type": "cooling_degradation",
            "sensor_corruption_type": "none",
            "fault_severity": 0.0,
        },
        {
            "simulation_run_id": "run-a",
            "asset_id": "asset-1",
            "timestamp": datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
            "fault_active": True,
            "fault_type": "cooling_degradation",
            "sensor_corruption_type": "none",
            "fault_severity": 0.5,
        },
    ]
    splits = {"train": ["run-a"], "validation": [], "test": []}

    rows = build_label_rows(ground_truth_rows, splits)

    assert rows[0].class_label == "healthy"
    assert rows[0].is_anomalous is False
    assert rows[0].fault_severity is None
    assert rows[1].class_label == "cooling_degradation"
    assert rows[1].is_anomalous is True
    assert rows[1].fault_severity == 0.5
    assert rows[0].split == "train"
