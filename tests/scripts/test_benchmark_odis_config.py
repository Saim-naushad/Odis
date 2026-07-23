"""Unit tests for scripts.benchmark_odis.config — no live services."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts.benchmark_odis.config import (
    REAL_ASSET_IDS,
    ConfigError,
    RunConfig,
    make_run_id,
    validate_config,
)


def _config(**overrides: object) -> RunConfig:
    defaults: dict[str, object] = {
        "run_id": "20260101000000-cooling-degradation-1a-r0",
        "mode": "performance",
        "scenario": "cooling_degradation",
        "asset_count": 1,
        "duration_seconds": 60.0,
        "kafka_publish_interval_seconds": 1.1,
        "kafka_sample_interval_seconds": 10.0,
        "transport": "kafka+http",
        "output_dir": Path("benchmark-results"),
    }
    defaults.update(overrides)
    return RunConfig(**defaults)  # type: ignore[arg-type]


def test_make_run_id_is_deterministic_given_the_same_clock_reading() -> None:
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    first = make_run_id(
        scenario="cooling_degradation", asset_count=10, repetition_index=1, now=now
    )
    second = make_run_id(
        scenario="cooling_degradation", asset_count=10, repetition_index=1, now=now
    )
    assert first == second


def test_make_run_id_has_no_uppercase_characters() -> None:
    """Also used as a Docker Compose project name, which rejects uppercase."""
    now = datetime(2026, 1, 1, 12, 30, 45, tzinfo=UTC)
    run_id = make_run_id(
        scenario="cooling_degradation", asset_count=1, repetition_index=0, now=now
    )
    assert run_id == run_id.lower()


def test_asset_ids_uses_real_stacks_first_then_bench_named_synthetic_ids() -> None:
    config = _config(asset_count=6)
    ids = config.asset_ids()
    assert ids[:4] == REAL_ASSET_IDS
    assert ids[4:] == ("fuel-cell-stack-bench-001", "fuel-cell-stack-bench-002")


def test_asset_ids_truncates_real_stacks_when_fewer_requested() -> None:
    config = _config(asset_count=2)
    assert config.asset_ids() == REAL_ASSET_IDS[:2]


def test_compose_project_name_is_unique_per_run_id() -> None:
    config = _config(run_id="abc")
    assert config.compose_project_name() == "odis-benchmark-abc"


def test_validate_config_rejects_cooling_degradation_with_kafka_only_transport() -> (
    None
):
    config = _config(scenario="cooling_degradation", transport="kafka")
    with pytest.raises(ConfigError, match="kafka\\+http"):
        validate_config(config)


def test_validate_config_allows_normal_operation_with_kafka_only_transport() -> None:
    config = _config(scenario="normal_operation", transport="kafka")
    validate_config(config)  # must not raise


def test_validate_config_rejects_non_positive_duration() -> None:
    config = _config(duration_seconds=0.0)
    with pytest.raises(ConfigError, match="duration_seconds"):
        validate_config(config)


def test_validate_config_rejects_zero_assets() -> None:
    config = _config(asset_count=0)
    with pytest.raises(ConfigError, match="asset_count"):
        validate_config(config)


def test_cli_defaults_produce_a_valid_config() -> None:
    """Argument parsing and validation must agree with each other before any
    Docker interaction is attempted — cheap enough to run every time,
    unlike tests/integration/test_benchmark_odis_smoke.py's real stack run."""
    from scripts.benchmark_odis.__main__ import _parse_args, build_config

    args = _parse_args([])
    config = build_config(args)
    validate_config(config)  # must not raise

