"""Run configuration for one deterministic, offline Plant Alpha simulation run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from backend.simulator.dataset.operating_conditions import OperatingConditions


class DatasetScenario(StrEnum):
    """Scenarios this dataset kernel can drive.

    Values intentionally match `backend.simulator.scenario_registry` names —
    this is the same fault vocabulary the live simulator uses, not a parallel
    one. Membrane dehydration and combined faults are out of scope for
    PR161 (see the repository audit's fault feasibility matrix); adding them
    means extending this enum, not working around it.
    """

    NORMAL_OPERATION = "normal_operation"
    COOLING_DEGRADATION = "cooling_degradation"
    HYDROGEN_SUPPLY_ISSUE = "hydrogen_supply_issue"
    SENSOR_ANOMALY = "sensor_anomaly"


_FAULT_SCENARIOS = frozenset(
    {
        DatasetScenario.COOLING_DEGRADATION,
        DatasetScenario.HYDROGEN_SUPPLY_ISSUE,
        DatasetScenario.SENSOR_ANOMALY,
    }
)


@dataclass(frozen=True)
class RunConfig:
    """Configuration for one offline Plant Alpha simulation run.

    Immutable fields: all.

    Severity semantics: `0.0` means no fault effect and is only valid for a
    healthy (`normal_operation`) run; `1.0` means the maximum configured
    fault effect (see `scenario_mapping.py`). A fault run must use a
    strictly positive severity — a zero-severity fault run would be
    healthy-equivalent in every physical respect while still carrying a
    positive `fault_type` label, which is exactly the kind of mislabeled
    sample this dataset contract must not produce. Subtle faults should use
    a small positive severity (e.g. `0.05`), not `0.0`. Never interpret
    `fault_severity` as remaining health.

    `seed` governs `operating_conditions` resolution (see
    `run_template.resolve_run_config`) and per-sample sensor-noise draws
    (see `runner.iter_samples`) via two independent `random.Random` streams
    derived from it — never Python's global random state. The underlying
    physics itself has no randomness (see
    `backend.simulator.machine._micro_variation`), so a `RunConfig`
    constructed directly (bypassing `resolve_run_config`) with the default
    `operating_conditions` is fully deterministic regardless of `seed`.

    `operating_conditions` holds *resolved* concrete values, not sampling
    ranges — the run must be reproducible from `RunConfig` alone, with no
    resampling ambiguity. Its default reproduces the pre-PR163 dataset-run
    trajectory exactly (see `operating_conditions.OperatingConditions`).

    **`fault_duration_sim_seconds` names the fault's ramp duration, not its
    total lifetime (PR167 correction)**: `fault_start_sim_seconds` names
    when a fault begins; over the following `fault_duration_sim_seconds`
    seconds it ramps from healthy to the configured maximum severity, and
    then — deliberately, matching PR161's documented physical behavior of
    never resetting `cooling_efficiency`/`fuel_supply_factor`/`sensor_bias`
    — it stays fully applied at that maximum for the rest of the run. There
    is no recovery. The persisted schema field keeps its original name for
    compatibility with already-generated dataset artifacts; do not read it
    as "how long the fault lasts." A future recovery scenario must be a
    separate, explicit policy with its own physical-restoration and
    ground-truth states, not an implication of this one. See
    `runner.iter_samples` and `ground_truth.compute_ground_truth`.
    """

    simulation_run_id: str
    seed: int
    scenario_name: DatasetScenario
    target_asset_id: str
    duration_sim_seconds: float
    dt_seconds: float
    run_start_time: datetime
    fault_start_sim_seconds: float | None = None
    fault_duration_sim_seconds: float | None = None
    fault_severity: float = 0.0
    operating_conditions: OperatingConditions = field(
        default_factory=OperatingConditions
    )

    def __post_init__(self) -> None:
        if not self.simulation_run_id:
            raise ValueError("simulation_run_id must not be empty")
        if not self.target_asset_id:
            raise ValueError("target_asset_id must not be empty")
        if self.duration_sim_seconds <= 0:
            raise ValueError("duration_sim_seconds must be positive")
        if self.dt_seconds <= 0:
            raise ValueError("dt_seconds must be positive")
        if self.run_start_time.tzinfo is None:
            raise ValueError("run_start_time must be timezone-aware")
        if not 0.0 <= self.fault_severity <= 1.0:
            raise ValueError("fault_severity must be within [0.0, 1.0]")

        if self.scenario_name in _FAULT_SCENARIOS:
            self._validate_fault_window()
        else:
            self._validate_no_fault_window()

    def _validate_no_fault_window(self) -> None:
        if (
            self.fault_start_sim_seconds is not None
            or self.fault_duration_sim_seconds is not None
        ):
            raise ValueError(
                f"{self.scenario_name} does not support a fault window"
            )
        if self.fault_severity != 0.0:
            raise ValueError(f"{self.scenario_name} must use fault_severity=0.0")

    def _validate_fault_window(self) -> None:
        if self.fault_severity <= 0.0:
            raise ValueError(
                f"{self.scenario_name} requires fault_severity > 0.0; a "
                "zero-severity fault run would be healthy-equivalent while "
                "still carrying a positive fault label"
            )
        if self.fault_start_sim_seconds is None:
            raise ValueError("fault_start_sim_seconds is required for a fault run")
        if self.fault_duration_sim_seconds is None:
            raise ValueError(
                "fault_duration_sim_seconds is required for a fault run"
            )
        if self.fault_start_sim_seconds < 0:
            raise ValueError("fault_start_sim_seconds must be non-negative")
        if self.fault_duration_sim_seconds <= 0:
            raise ValueError("fault_duration_sim_seconds must be positive")

        ramp_end = self.fault_start_sim_seconds + self.fault_duration_sim_seconds
        if ramp_end > self.duration_sim_seconds:
            raise ValueError(
                "fault ramp extends beyond duration_sim_seconds; the ramp "
                "must complete within the run (no clipping policy is "
                "implemented) — the fault itself remains active from "
                "fault_start_sim_seconds through the end of the run"
            )

    @property
    def ramp_end_sim_seconds(self) -> float | None:
        """When the fault ramp reaches the configured maximum severity, or
        `None` for a healthy run. **Not** the end of the fault — per the
        no-recovery policy (see this class's docstring), the fault stays
        active at maximum severity from this point through the end of the
        run."""
        if (
            self.fault_start_sim_seconds is None
            or self.fault_duration_sim_seconds is None
        ):
            return None
        return self.fault_start_sim_seconds + self.fault_duration_sim_seconds
