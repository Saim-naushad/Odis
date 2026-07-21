"""Sanity check for `tiny_runtime_fixture` itself."""

from __future__ import annotations

from .conftest import TinyRuntimeFixture


def test_fixture_builds_a_loadable_system(
    tiny_runtime_fixture: TinyRuntimeFixture,
) -> None:
    system = tiny_runtime_fixture.system
    assert system.feature_group == "D"
    assert set(system.class_order) == {
        "healthy",
        "cooling_degradation",
        "hydrogen_supply_issue",
        "sensor_anomaly",
    }
    assert system.alert_policy_config.entry_probability == 0.60
