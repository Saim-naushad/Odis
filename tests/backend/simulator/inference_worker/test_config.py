"""`InferenceWorkerSettings` specification (PR177 spec sections 13, 17
"Configuration")."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.simulator.inference_worker.config import InferenceWorkerSettings


def test_defaults_are_valid() -> None:
    settings = InferenceWorkerSettings()
    assert settings.bundle_dir == Path("artifacts/models/plant_alpha_fault_v1")
    assert settings.consumer_group_id == "odis-fault-inference-worker"
    assert settings.publish_max_retries == 3


def test_empty_input_topic_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InferenceWorkerSettings(input_topic="")


def test_empty_bootstrap_servers_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InferenceWorkerSettings(kafka_bootstrap_servers="")


def test_non_positive_assembly_timeout_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InferenceWorkerSettings(assembly_timeout_seconds=0)


def test_non_positive_max_buffered_timestamps_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InferenceWorkerSettings(max_buffered_timestamps_per_asset=0)


def test_negative_publish_max_retries_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InferenceWorkerSettings(publish_max_retries=-1)


def test_zero_publish_max_retries_is_allowed() -> None:
    settings = InferenceWorkerSettings(publish_max_retries=0)
    assert settings.publish_max_retries == 0


def test_environment_overrides_are_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-1:9092,kafka-2:9092")
    monkeypatch.setenv("FAULT_INFERENCE_INPUT_TOPIC", "custom.input.v1")
    monkeypatch.setenv("FAULT_INFERENCE_CONSUMER_GROUP_ID", "custom-group")
    monkeypatch.setenv("FAULT_INFERENCE_ASSEMBLY_TIMEOUT_SECONDS", "45.5")

    settings = InferenceWorkerSettings()

    assert settings.kafka_bootstrap_servers == "kafka-1:9092,kafka-2:9092"
    assert settings.input_topic == "custom.input.v1"
    assert settings.consumer_group_id == "custom-group"
    assert settings.assembly_timeout_seconds == 45.5
