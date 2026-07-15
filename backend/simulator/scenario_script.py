"""Timed scenario scripts for presentation and realistic demos."""

from __future__ import annotations

from dataclasses import dataclass

from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.base import Scenario
from backend.simulator.scenarios.cooling_degradation import CoolingDegradationScenario
from backend.simulator.scenarios.hydrogen_supply_issue import (
    HydrogenSupplyIssueScenario,
)
from backend.simulator.scenarios.normal_operation import NormalOperationScenario
from backend.simulator.scenarios.recovery import RecoveryScenario
from backend.simulator.scenarios.sensor_anomaly import SensorAnomalyScenario


@dataclass(frozen=True)
class ScenarioPhase:
    name: str
    duration_sim_seconds: float
    target_asset_id: str = "fuel-cell-stack-01"


@dataclass(frozen=True)
class ScriptCadence:
    """A scripted scenario's preferred publish cadence, in real seconds.

    Scripts that need a short, predictable wall-clock runtime (e.g. a
    presentation walkthrough) own their cadence here instead of relying on
    the platform's default cadence — see `cadence_for_script`.
    """

    core_publish_interval_seconds: float
    derived_publish_interval_seconds: float
    sim_dt_seconds: float


# `demo_presentation` targets a short, deterministic walkthrough: healthy
# baseline -> cooling degradation -> warning -> critical -> recovery. Two
# platform behaviors (outside the simulator, not changed here) drive this
# cadence choice:
#  - health-status classification needs >=8 core samples of a consistent
#    trend before it trusts a directional change (`trend_detector.py` /
#    `time_series_analysis.py`), so a faster-than-default core interval is
#    what makes each beat land in a couple of minutes instead of ~4.
#  - that same window is sensitive to the simulator's own sinusoidal load
#    cycle (`NormalOperationScenario`, 300 sim-seconds/cycle) bleeding into
#    the "current" measurement, which can compete with the temperature
#    fault signal for which measurement reasoning treats as primary. A
#    higher sim:real ratio (via `sim_dt_seconds`, decoupled from the core
#    interval) compresses several full load cycles into each phase so that
#    competing signal averages out, without slowing down the real-time
#    reasoning cadence. Empirically, 5s/15s (3x ratio, the default ratio)
#    was fast enough to trigger flaky primary-measurement selection across
#    otherwise-identical clean runs; 10s/90s (9x ratio) was not.
#  - recovering to a *held, stable* NORMAL reading is not simply a function
#    of the physical ramp finishing: the fault's peak (and the resulting
#    CRITICAL/WARNING classification) lags a first-order-lag phase boundary
#    by ~20-30s, and — separate from the simulator entirely — the
#    platform's trend window and append-only notifications take roughly
#    200s of real time within `recovery` to age out the stale fault
#    classification and settle, regardless of how long the recovery ramp
#    itself is (confirmed empirically across two clean runs with different
#    recovery durations: both showed CRITICAL ~20s into recovery lasting
#    ~33s, then WARNING persisting until ~205-220s into recovery before
#    settling). `recovery`'s duration below is sized for that settling time
#    plus a hold, not just the physical ramp.
_PRESENTATION_CADENCE = ScriptCadence(
    core_publish_interval_seconds=10.0,
    derived_publish_interval_seconds=30.0,
    sim_dt_seconds=90.0,
)

_SCRIPT_CADENCE: dict[str, ScriptCadence] = {
    "demo_presentation": _PRESENTATION_CADENCE,
}


def cadence_for_script(script_name: str) -> ScriptCadence | None:
    """Return the preferred cadence for a scripted scenario, if it has one.

    Returns `None` for scripts (like `demo_realistic`) that intentionally run
    at the platform's default/configured cadence rather than a bespoke one.
    """
    return _SCRIPT_CADENCE.get(script_name)


# Real-time durations below assume `_PRESENTATION_CADENCE` (a 9x sim:real
# ratio). Measured against two independent clean-database runs
# (`docker compose down -v` then `--profile demo up --build -d`),
# watching `[demo:demo_presentation] phase changed -> ...` log lines
# alongside `GET /monitoring/assets/fuel-cell-stack-01/digital-twin`:
#   00:00 normal_operation    (~30s)  -- healthy baseline (NORMAL, score 90)
#   00:30 cooling_degradation (~120s) -- ramp in progress; health dips to a
#                                         mild NORMAL(80), fault not yet
#                                         classified as WARNING/CRITICAL
#   02:30 recovery            (~250s) -- CRITICAL appears ~20s in (score 35,
#                                         holding ~33s — the fault's physical
#                                         peak lags the phase boundary),
#                                         then WARNING until the platform's
#                                         trend/notification state settles
#                                         (~205-220s in), then holds NORMAL
#   06:40 script holds (no further phase)
PRESENTATION_PHASES: tuple[ScenarioPhase, ...] = (
    ScenarioPhase("normal_operation", 270),
    ScenarioPhase("cooling_degradation", 1080),
    ScenarioPhase("recovery", 2250),
)

REALISTIC_PHASES: tuple[ScenarioPhase, ...] = (
    ScenarioPhase("normal_operation", 30 * 60),
    ScenarioPhase("cooling_degradation", 45 * 60),
    ScenarioPhase("recovery", 30 * 60),
    ScenarioPhase("hydrogen_supply_issue", 30 * 60),
    ScenarioPhase("recovery", 30 * 60),
    ScenarioPhase("sensor_anomaly", 30 * 60, "fuel-cell-stack-02"),
    ScenarioPhase("recovery", 30 * 60, "fuel-cell-stack-02"),
)


class ScenarioScriptRunner:
    """Advance through scripted scenario phases using simulation time."""

    name: str

    def __init__(self, *, script_name: str, phases: tuple[ScenarioPhase, ...]) -> None:
        self.name = script_name
        self._phases = phases
        self._phase_index = 0
        self._phase_elapsed = 0.0
        self._active = self._build_phase(self._phases[0])

    @property
    def current_phase_name(self) -> str:
        return self._phases[self._phase_index].name

    def _build_phase(self, phase: ScenarioPhase) -> Scenario:
        if phase.name == "normal_operation":
            return NormalOperationScenario()
        if phase.name == "cooling_degradation":
            return CoolingDegradationScenario(
                target_asset_id=phase.target_asset_id,
                duration_sim_seconds=phase.duration_sim_seconds,
            )
        if phase.name == "hydrogen_supply_issue":
            return HydrogenSupplyIssueScenario(
                target_asset_id=phase.target_asset_id,
                duration_sim_seconds=phase.duration_sim_seconds,
            )
        if phase.name == "sensor_anomaly":
            return SensorAnomalyScenario(
                target_asset_id=phase.target_asset_id,
                duration_sim_seconds=phase.duration_sim_seconds,
            )
        if phase.name == "recovery":
            return RecoveryScenario(
                target_asset_id=phase.target_asset_id,
                duration_sim_seconds=phase.duration_sim_seconds,
            )
        msg = f"unsupported scenario phase: {phase.name}"
        raise ValueError(msg)

    def tick(self, fleet: PlantAlphaFleet, dt_seconds: float) -> None:
        self._active.tick(fleet, dt_seconds)
        self._phase_elapsed += dt_seconds
        current = self._phases[self._phase_index]
        if self._phase_elapsed < current.duration_sim_seconds:
            return
        if self._phase_index >= len(self._phases) - 1:
            return
        self._phase_index += 1
        self._phase_elapsed = 0.0
        next_phase = self._phases[self._phase_index]
        self._active = self._build_phase(next_phase)
        # Printed so a screen recording has an on-screen (console) cue for
        # exactly when each demo beat starts, without doing wall-clock math
        # against PRESENTATION_PHASES by hand.
        print(
            f"[demo:{self.name}] phase changed -> {next_phase.name} "
            f"(target={next_phase.target_asset_id})"
        )


def build_script_runner(script_name: str) -> ScenarioScriptRunner:
    if script_name == "demo_presentation":
        return ScenarioScriptRunner(
            script_name=script_name,
            phases=PRESENTATION_PHASES,
        )
    if script_name == "demo_realistic":
        return ScenarioScriptRunner(
            script_name=script_name,
            phases=REALISTIC_PHASES,
        )
    msg = f"unsupported scenario script: {script_name}"
    raise ValueError(msg)
