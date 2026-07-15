"""Tests for scripted scenario cadence ownership."""

from __future__ import annotations

from backend.simulator.__main__ import _apply_script_cadence
from backend.simulator.config import SimulatorSettings
from backend.simulator.scenario_script import (
    PRESENTATION_PHASES,
    cadence_for_script,
)


def test_cadence_for_script_returns_none_for_realistic() -> None:
    assert cadence_for_script("demo_realistic") is None


def test_cadence_for_script_returns_none_for_unscripted_scenario() -> None:
    assert cadence_for_script("normal_operation") is None


def test_cadence_for_script_returns_presentation_cadence() -> None:
    cadence = cadence_for_script("demo_presentation")
    assert cadence is not None
    assert cadence.core_publish_interval_seconds == 10.0
    assert cadence.derived_publish_interval_seconds == 30.0
    assert cadence.sim_dt_seconds == 90.0


def test_presentation_phases_cover_the_three_named_beats() -> None:
    assert [phase.name for phase in PRESENTATION_PHASES] == [
        "normal_operation",
        "cooling_degradation",
        "recovery",
    ]


def test_apply_script_cadence_overrides_defaults_for_presentation() -> None:
    settings = SimulatorSettings()
    updated = _apply_script_cadence(settings, "demo_presentation")
    assert updated.core_publish_interval_seconds == 10.0
    assert updated.derived_publish_interval_seconds == 30.0
    assert updated.sim_dt_seconds == 90.0


def test_apply_script_cadence_leaves_realistic_untouched() -> None:
    settings = SimulatorSettings()
    updated = _apply_script_cadence(settings, "demo_realistic")
    assert updated.core_publish_interval_seconds == 15.0
    assert updated.derived_publish_interval_seconds == 60.0
    assert updated.sim_dt_seconds == 45.0


def test_apply_script_cadence_respects_explicit_operator_override() -> None:
    settings = SimulatorSettings().model_copy(
        update={"core_publish_interval_seconds": 20.0},
    )
    updated = _apply_script_cadence(settings, "demo_presentation")
    assert updated.core_publish_interval_seconds == 20.0
    # Fields the operator didn't touch still pick up the script's cadence.
    assert updated.derived_publish_interval_seconds == 30.0
    assert updated.sim_dt_seconds == 90.0
