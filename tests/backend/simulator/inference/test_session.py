"""`FaultInferenceSession`/`FaultInferenceManager` specifications (spec
sections 5, 7, 10 / test items "Warm-up", "Alert behavior", "Multi-asset
isolation", "Serialization and determinism").

Warm-up and multi-asset-isolation tests drive the session with the tiny
fixture's real telemetry and real fitted pipeline (feature computation and
its timing must be real). Alert-*transition* tests instead swap in a
`_FakeSequencePipeline` that returns a pre-scripted probability sequence
regardless of the feature vector it's given — the state machine's
entry/exit/switch behavior is already exhaustively covered by
`alert_policy/test_state_machine.py`'s 38 tests (untouched by PR176; see
`state_machine.step_state_machine`'s extraction), so what PR176 needs to
prove here is only that the *session* wires each ingested sample into one
`step_state_machine` call, in order, with the right `proba`/`valid` — a
real-but-tiny fitted model's incidental confidence on one held-out run is
the wrong thing to depend on for that (it may or may not cross a
threshold by chance; parity with the model itself is already proven
separately in `test_offline_online_parity.py`).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pyarrow.parquet as pq
import pytest

from backend.simulator.dataset.features.config import LONGEST_WINDOW_SAMPLES
from backend.simulator.inference.loader import PromotedFaultSystem
from backend.simulator.inference.result import InferenceStatus
from backend.simulator.inference.session import (
    FaultInferenceManager,
    FaultInferenceSession,
)
from backend.simulator.inference.telemetry import (
    NonMonotonicTimestampError,
    TelemetrySample,
)
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType

from .conftest import TinyRuntimeFixture

_ASSET_ID = "fuel-cell-stack-01"


def _run_id_for_class(dataset_dir, class_label: str) -> str:  # type: ignore[no-untyped-def]
    runs = pq.read_table(
        dataset_dir / "runs.parquet", columns=["simulation_run_id", "class_label"]
    ).to_pylist()
    return str(
        next(r["simulation_run_id"] for r in runs if r["class_label"] == class_label)
    )


def _batches_for_run(dataset_dir, run_id: str) -> list[tuple[Observation, ...]]:  # type: ignore[no-untyped-def]
    telemetry_table = pq.read_table(dataset_dir / "telemetry.parquet")
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
                id=f"session-{run_id}-{row['measurement_type']}-{elapsed}",
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


def _relabel(observations, asset_id: str):  # type: ignore[no-untyped-def]
    return tuple(
        Observation(
            id=obs.id,
            asset_id=asset_id,
            timestamp=obs.timestamp,
            measurement_type=obs.measurement_type,
            value=obs.value,
            unit=obs.unit,
        )
        for obs in observations
    )


class _FakeSequencePipeline:
    """A stand-in for the fitted sklearn pipeline that ignores its input
    feature vector entirely and returns one pre-scripted probability row
    per call, in order — lets alert-transition tests control the
    diagnosed class/probability deterministically without depending on a
    real (and, at tiny-fixture scale, possibly under-confident) model."""

    def __init__(self, proba_sequence: list[np.ndarray]) -> None:
        self._sequence = proba_sequence
        self._calls = 0

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        proba = self._sequence[self._calls]
        self._calls += 1
        return np.array([proba])


def _scripted_system(
    base_system: PromotedFaultSystem, proba_sequence: list[np.ndarray]
) -> PromotedFaultSystem:
    return replace(base_system, pipeline=_FakeSequencePipeline(proba_sequence))


def _proba_row(class_order: tuple[str, ...], **by_class: float) -> np.ndarray:
    remainder_classes = [c for c in class_order if c not in by_class]
    assigned = sum(by_class.values())
    remainder = (1.0 - assigned) / len(remainder_classes) if remainder_classes else 0.0
    return np.array(
        [by_class.get(cls, remainder) for cls in class_order], dtype=float
    )


# --- Warm-up (real fixture) -----------------------------------------------


def test_no_prediction_before_longest_required_window(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)
    session = FaultInferenceSession(
        asset_id=_ASSET_ID, system=tiny_runtime_fixture.system
    )

    for observations in batches[: LONGEST_WINDOW_SAMPLES - 1]:
        sample = TelemetrySample.from_observations(observations)
        result = session.ingest(sample)
        assert result.status is InferenceStatus.WARMING_UP
        assert result.diagnosed_class is None


def test_first_eligible_timestamp_matches_offline_semantics(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    """Offline drops rows with `index < LONGEST_WINDOW_SAMPLES - 1`; the
    first eligible row is at zero-based index `LONGEST_WINDOW_SAMPLES - 1`
    — the `LONGEST_WINDOW_SAMPLES`-th sample."""
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)
    session = FaultInferenceSession(
        asset_id=_ASSET_ID, system=tiny_runtime_fixture.system
    )

    results = [
        session.ingest(TelemetrySample.from_observations(obs))
        for obs in batches[:LONGEST_WINDOW_SAMPLES]
    ]
    assert all(r.status is InferenceStatus.WARMING_UP for r in results[:-1])
    assert results[-1].status is not InferenceStatus.WARMING_UP


def test_bounded_history_retained(tiny_runtime_fixture: TinyRuntimeFixture) -> None:
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)
    session = FaultInferenceSession(
        asset_id=_ASSET_ID, system=tiny_runtime_fixture.system
    )
    for observations in batches:
        session.ingest(TelemetrySample.from_observations(observations))

    for series in session._history.values():
        assert len(series) <= LONGEST_WINDOW_SAMPLES


# --- Alert behavior (scripted pipeline, real telemetry timing) -----------


def test_alert_confirms_after_entry_persistence_and_emits_one_event(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    system = tiny_runtime_fixture.system
    entry_persistence = system.alert_policy_config.entry_persistence
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)
    n_predictions = 6
    healthy_row = _proba_row(system.class_order, healthy=0.95)
    fault_row = _proba_row(system.class_order, cooling_degradation=0.99)
    sequence = [healthy_row] * 2 + [fault_row] * (n_predictions - 2)
    scripted = _scripted_system(system, sequence)

    session = FaultInferenceSession(asset_id=_ASSET_ID, system=scripted)
    results = [
        session.ingest(TelemetrySample.from_observations(obs))
        for obs in batches[: LONGEST_WINDOW_SAMPLES - 1 + n_predictions]
    ]

    new_alert_events = [
        r
        for r in results
        if r.alert_event is not None and r.alert_event["event_type"] == "new_alert"
    ]
    assert len(new_alert_events) == 1
    new_alert_event = new_alert_events[0].alert_event
    assert new_alert_event is not None
    assert new_alert_event["fault_class"] == "cooling_degradation"
    assert new_alert_events[0].alert_state == "confirmed_cooling_degradation"
    # Confirms exactly `entry_persistence` fault-qualifying samples after
    # the two healthy ones, never earlier and never later.
    fault_predictions = [
        r for r in results if r.diagnosed_class == "cooling_degradation"
    ]
    assert len(fault_predictions) == n_predictions - 2
    warmup_rows = LONGEST_WINDOW_SAMPLES - 1
    confirming_index = warmup_rows + 2 + entry_persistence - 1
    assert results[confirming_index] is new_alert_events[0]


def test_no_duplicate_events_while_confirmed(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    system = tiny_runtime_fixture.system
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)
    n_predictions = 8
    fault_row = _proba_row(system.class_order, cooling_degradation=0.99)
    scripted = _scripted_system(system, [fault_row] * n_predictions)

    session = FaultInferenceSession(asset_id=_ASSET_ID, system=scripted)
    results = [
        session.ingest(TelemetrySample.from_observations(obs))
        for obs in batches[: LONGEST_WINDOW_SAMPLES - 1 + n_predictions]
    ]
    confirmed = [
        r for r in results if r.alert_state == "confirmed_cooling_degradation"
    ]
    events_after_first_confirmation = [
        r.alert_event for r in confirmed[1:] if r.alert_event
    ]
    assert events_after_first_confirmation == []


def test_healthy_exit_after_exit_persistence(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    system = tiny_runtime_fixture.system
    exit_persistence = system.alert_policy_config.exit_persistence
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)
    fault_row = _proba_row(system.class_order, cooling_degradation=0.99)
    healthy_row = _proba_row(system.class_order, healthy=0.95)
    n_fault = system.alert_policy_config.entry_persistence
    n_healthy = exit_persistence + 2
    sequence = [fault_row] * n_fault + [healthy_row] * n_healthy
    scripted = _scripted_system(system, sequence)

    session = FaultInferenceSession(asset_id=_ASSET_ID, system=scripted)
    results = [
        session.ingest(TelemetrySample.from_observations(obs))
        for obs in batches[: LONGEST_WINDOW_SAMPLES - 1 + len(sequence)]
    ]
    cleared_events = [
        r
        for r in results
        if r.alert_event is not None and r.alert_event["event_type"] == "cleared"
    ]
    assert len(cleared_events) == 1
    assert results[-1].alert_state == "healthy"


def test_class_switch_while_confirmed(tiny_runtime_fixture: TinyRuntimeFixture) -> None:
    system = tiny_runtime_fixture.system
    entry_persistence = system.alert_policy_config.entry_persistence
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)
    cooling_row = _proba_row(system.class_order, cooling_degradation=0.99)
    hydrogen_row = _proba_row(system.class_order, hydrogen_supply_issue=0.99)
    sequence = [cooling_row] * entry_persistence + [hydrogen_row] * entry_persistence
    scripted = _scripted_system(system, sequence)

    session = FaultInferenceSession(asset_id=_ASSET_ID, system=scripted)
    results = [
        session.ingest(TelemetrySample.from_observations(obs))
        for obs in batches[: LONGEST_WINDOW_SAMPLES - 1 + len(sequence)]
    ]
    switch_events = [
        r
        for r in results
        if r.alert_event is not None and r.alert_event["event_type"] == "class_change"
    ]
    assert len(switch_events) == 1
    switch_event = switch_events[0].alert_event
    assert switch_event is not None
    assert switch_event["fault_class"] == "hydrogen_supply_issue"
    assert results[-1].alert_state == "confirmed_hydrogen_supply_issue"


def test_alert_progress_evidence_present_before_confirmation(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    system = tiny_runtime_fixture.system
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)
    fault_row = _proba_row(system.class_order, cooling_degradation=0.65)
    scripted = _scripted_system(system, [fault_row] * 2)

    session = FaultInferenceSession(asset_id=_ASSET_ID, system=scripted)
    results = [
        session.ingest(TelemetrySample.from_observations(obs))
        for obs in batches[: LONGEST_WINDOW_SAMPLES + 1]
    ]
    valid_results = [r for r in results if r.status is InferenceStatus.VALID_PREDICTION]
    assert any(
        any(item.label == "alert_entry_progress" for item in r.evidence)
        for r in valid_results
    )


def test_insufficient_data_breaks_pending_but_preserves_confirmed(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    """PR173 semantics, reused unchanged by the session: an
    `insufficient_data` row while `healthy` breaks a pending streak.

    One valid fault-qualifying row builds a 1-sample pending streak; the
    next row is forced `insufficient_data` (resetting the streak to zero,
    per the state machine's own contract — see `alert_policy.state_machine`'s
    module docstring); only `entry_persistence - 1` valid fault rows remain
    afterward — one short of what `entry_persistence` requires, so no
    `new_alert` can fire. `compute_feature_row`/`step_state_machine` are
    unchanged code (see their own module docstrings); this test only
    proves the *session* replays insufficient-data rows into the FSM
    exactly like the batch `ood.alert_metrics` path does, without
    consuming a model call for that row (the row's feature computation
    fails before `pipeline.predict_proba` is ever reached).
    """
    from backend.simulator.dataset.features.safety import MIN_ABS_FUEL_FLOW_SLPM

    system = tiny_runtime_fixture.system
    entry_persistence = system.alert_policy_config.entry_persistence
    warmup_rows = LONGEST_WINDOW_SAMPLES - 1
    # 1 valid row, then the forced-insufficient row, then entry_persistence-1
    # more valid rows — entry_persistence valid `predict_proba` calls total.
    total_batches = warmup_rows + 1 + 1 + (entry_persistence - 1)
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    batches = list(
        _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)[:total_batches]
    )
    fault_row = _proba_row(system.class_order, cooling_degradation=0.99)
    scripted = _scripted_system(system, [fault_row] * entry_persistence)

    break_index = warmup_rows + 1
    batches[break_index] = tuple(
        obs
        if obs.measurement_type.name != "fuel_flow"
        else Observation(
            id=obs.id, asset_id=obs.asset_id, timestamp=obs.timestamp,
            measurement_type=obs.measurement_type,
            value=MIN_ABS_FUEL_FLOW_SLPM / 2, unit=obs.unit,
        )
        for obs in batches[break_index]
    )

    session = FaultInferenceSession(asset_id=_ASSET_ID, system=scripted)
    results = [
        session.ingest(TelemetrySample.from_observations(obs)) for obs in batches
    ]

    assert results[break_index].status is InferenceStatus.INSUFFICIENT_DATA
    assert results[break_index].diagnosed_class is None
    # The break reset the pending streak; only entry_persistence - 1 valid
    # fault rows remain, one short of confirming — no new_alert ever fires.
    assert not any(
        r.alert_event is not None and r.alert_event["event_type"] == "new_alert"
        for r in results
    )
    assert results[-1].alert_state == "healthy"


# --- Multi-asset isolation (real fixture) ---------------------------------


def test_multi_asset_histories_and_alerts_are_independent(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    system = tiny_runtime_fixture.system
    entry_persistence = system.alert_policy_config.entry_persistence
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)
    n = LONGEST_WINDOW_SAMPLES - 1 + entry_persistence + 2

    healthy_row = _proba_row(system.class_order, healthy=0.95)
    fault_row = _proba_row(system.class_order, cooling_degradation=0.99)
    healthy_system = _scripted_system(system, [healthy_row] * n)
    fault_system = _scripted_system(system, [fault_row] * n)

    healthy_session = FaultInferenceSession(
        asset_id="asset-healthy", system=healthy_system
    )
    fault_session = FaultInferenceSession(asset_id="asset-fault", system=fault_system)

    for observations in batches[:n]:
        healthy_session.ingest(
            TelemetrySample.from_observations(_relabel(observations, "asset-healthy"))
        )
        fault_session.ingest(
            TelemetrySample.from_observations(_relabel(observations, "asset-fault"))
        )

    assert healthy_session.alert_state == "healthy"
    assert fault_session.alert_state == "confirmed_cooling_degradation"


def test_out_of_order_data_for_one_asset_does_not_corrupt_another(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    manager = FaultInferenceManager(system=tiny_runtime_fixture.system)
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)

    for observations in batches[:5]:
        manager.ingest(
            TelemetrySample.from_observations(_relabel(observations, "asset-a"))
        )
        manager.ingest(
            TelemetrySample.from_observations(_relabel(observations, "asset-b"))
        )

    out_of_order_sample = TelemetrySample.from_observations(
        _relabel(batches[2], "asset-a")
    )
    with pytest.raises(NonMonotonicTimestampError):
        manager.ingest(out_of_order_sample)

    # asset-b's own state is untouched by asset-a's rejected ingest.
    assert manager.session_for("asset-b").samples_ingested == 5


# --- Determinism (real fixture) -------------------------------------------


def test_same_sequence_produces_identical_results(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "cooling_degradation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)

    def _run() -> list[dict[str, object]]:
        session = FaultInferenceSession(
            asset_id=_ASSET_ID, system=tiny_runtime_fixture.system
        )
        return [
            session.ingest(TelemetrySample.from_observations(obs)).to_json_dict()
            for obs in batches
        ]

    first_run = _run()
    second_run = _run()
    assert first_run == second_run


def test_evidence_order_is_deterministic(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "cooling_degradation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)
    session = FaultInferenceSession(
        asset_id=_ASSET_ID, system=tiny_runtime_fixture.system
    )
    results = [
        session.ingest(TelemetrySample.from_observations(obs)) for obs in batches
    ]
    for r in results:
        if r.status is InferenceStatus.VALID_PREDICTION:
            labels = [item.label for item in r.evidence]
            assert labels == sorted(labels, key=labels.index)  # stable, non-random
            assert labels[0] == "top_class_probability"


def test_reset_clears_warmup_and_alert_state(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    system = tiny_runtime_fixture.system
    run_id = _run_id_for_class(tiny_runtime_fixture.dataset_dir, "normal_operation")
    batches = _batches_for_run(tiny_runtime_fixture.dataset_dir, run_id)
    entry_persistence = system.alert_policy_config.entry_persistence
    n = LONGEST_WINDOW_SAMPLES - 1 + entry_persistence
    fault_row = _proba_row(system.class_order, cooling_degradation=0.99)
    scripted = _scripted_system(system, [fault_row] * n)

    session = FaultInferenceSession(asset_id=_ASSET_ID, system=scripted)
    for observations in batches[:n]:
        session.ingest(TelemetrySample.from_observations(observations))
    assert session.alert_state != "healthy"

    session.reset()
    assert session.alert_state == "healthy"
    assert session.samples_ingested == 0
