"""Count-reconciliation unit tests (PR181) — no live Kafka/DB required.

`KafkaObserver._handle` is exercised directly with synthetic message bytes,
never via a live consumer connection, so these stay fast unit tests.
"""

from __future__ import annotations

import json

from scripts.benchmark_odis.measurements import _parse_docker_memory
from scripts.benchmark_odis.observers import (
    ALERT_TRANSITIONS_TOPIC,
    INFERENCE_RESULTS_TOPIC,
    TELEMETRY_TOPIC,
    KafkaObserver,
)


def _observer() -> KafkaObserver:
    return KafkaObserver(bootstrap_servers="unused:0", group_id="unused")


def _telemetry_message(asset_id: str, measurement_name: str) -> bytes:
    return json.dumps(
        {
            "event_id": f"{asset_id}-{measurement_name}",
            "asset_id": asset_id,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "measurement_name": measurement_name,
        }
    ).encode("utf-8")


def test_eight_measurement_events_form_one_complete_sample() -> None:
    """Plant Alpha publishes 5 core + 3 derived measurements per asset per
    tick (`backend/simulator/telemetry.py`'s `_CORE_MEASUREMENT_SPECS` —
    stack_temperature/stack_pressure/current/voltage/hydrogen_flow — plus
    derived power_output/efficiency/coolant_flow) — 8 raw events per
    complete sample, confirmed against a real benchmark run's reconciled
    counts (608 raw telemetry events / 76 assembled samples = 8.0 exactly),
    correcting the commonly assumed "seven measurements per sample". The
    observer must count each raw measurement message individually, distinct
    from a 'complete sample' (one inference-result event per tick)."""
    observer = _observer()
    measurements = (
        "stack_temperature",
        "stack_pressure",
        "current",
        "voltage",
        "hydrogen_flow",
        "power_output",
        "efficiency",
        "coolant_flow",
    )
    for name in measurements:
        observer._handle(
            TELEMETRY_TOPIC, _telemetry_message("fuel-cell-stack-01", name)
        )

    assert observer.raw_telemetry_count == 8
    assert observer.raw_telemetry_count_by_asset["fuel-cell-stack-01"] == 8


def test_inference_result_counts_reconcile_by_status() -> None:
    observer = _observer()
    for status in ("warming_up", "warming_up", "valid_prediction", "insufficient_data"):
        payload = {
            "event_id": f"evt-{status}-{len(observer.inference_results)}",
            "asset_id": "fuel-cell-stack-01",
            "status": status,
            "occurred_at": "2026-01-01T00:00:01+00:00",
            "source_timestamp": "2026-01-01T00:00:00+00:00",
        }
        observer._handle(
            INFERENCE_RESULTS_TOPIC, json.dumps(payload).encode("utf-8")
        )

    assert len(observer.inference_results) == 4
    by_status = [r.status for r in observer.inference_results]
    assert by_status.count("warming_up") == 2
    assert by_status.count("valid_prediction") == 1
    assert by_status.count("insufficient_data") == 1


def test_malformed_kafka_message_is_counted_not_raised() -> None:
    observer = _observer()
    observer._handle(TELEMETRY_TOPIC, b"not valid json")
    assert observer.malformed_message_count == 1
    assert observer.raw_telemetry_count == 0


def test_first_confirmed_transition_ignores_class_changed_and_cleared() -> None:
    observer = _observer()
    for transition_type, occurred_offset_minutes in (
        ("class_changed", 5),
        ("confirmed", 1),
        ("cleared", 10),
    ):
        payload = {
            "event_id": f"evt-{transition_type}",
            "asset_id": "fuel-cell-stack-01",
            "transition_type": transition_type,
            "occurred_at": "2026-01-01T00:00:01+00:00",
            "source_timestamp": f"2026-01-01T00:{occurred_offset_minutes:02d}:00+00:00",
        }
        observer._handle(
            ALERT_TRANSITIONS_TOPIC, json.dumps(payload).encode("utf-8")
        )

    confirmed = observer.first_confirmed_transition("fuel-cell-stack-01")
    assert confirmed is not None
    assert confirmed.transition_type == "confirmed"


def test_parse_docker_memory_units() -> None:
    assert _parse_docker_memory("512MiB") == 512 * 1024 * 1024
    assert _parse_docker_memory("1.5GiB") == 1.5 * 1024 * 1024 * 1024
    assert _parse_docker_memory("200KiB") == 200 * 1024
