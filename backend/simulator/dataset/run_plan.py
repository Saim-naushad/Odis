"""Deterministic run planning: `DatasetSpec` -> ordered `PlannedRun`s.

Planning is pure and deterministic: the same `DatasetSpec` always produces
the same run IDs, seed assignments, target-asset assignments, and resolved
`RunConfig`s, in the same order. No `uuid4()`, no `datetime.now()`, no
global random state — run identity comes entirely from `dataset_id` +
scenario name + a sequential index.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.simulator.dataset.dataset_spec import DatasetSpec, ScenarioRunSpec
from backend.simulator.dataset.run_config import RunConfig
from backend.simulator.dataset.run_template import RunTemplate, resolve_run_config


@dataclass(frozen=True)
class PlannedRun:
    """One fully resolved run, ready for `runner.run`/`runner.iter_samples`."""

    simulation_run_id: str
    dataset_id: str
    class_label: str
    run_config: RunConfig


def _run_id(dataset_id: str, plan: ScenarioRunSpec, local_index: int) -> str:
    """Deterministic run id: `{dataset_id}-{scenario_name}-{local_index:04d}`."""
    return f"{dataset_id}-{plan.scenario_name.value}-{local_index:04d}"


def plan_runs(spec: DatasetSpec) -> tuple[PlannedRun, ...]:
    """Resolve `spec` into an ordered, deterministic tuple of `PlannedRun`.

    Iterates `spec.scenario_plans` in order; within each plan, seeds are
    consumed sequentially from `spec.seeds` (a flat, spec-wide list — the
    N-th planned run overall always gets `spec.seeds[N]`), and target
    assets round-robin over `spec.target_asset_ids` per scenario plan (so
    each class gets asset-balanced runs independently).

    Raises whatever `RunConfig`/`resolve_run_config` raises for an invalid
    fault-window/severity combination — planning happens entirely before
    any output is written, so an invalid spec never produces a partial
    dataset directory.
    """
    planned: list[PlannedRun] = []
    seed_cursor = 0

    for plan in spec.scenario_plans:
        for local_index in range(plan.run_count):
            seed = spec.seeds[seed_cursor]
            seed_cursor += 1
            target_asset_id = spec.target_asset_ids[
                local_index % len(spec.target_asset_ids)
            ]
            run_id = _run_id(spec.dataset_id, plan, local_index)

            template = RunTemplate(
                simulation_run_id=run_id,
                seed=seed,
                scenario_name=plan.scenario_name,
                target_asset_id=target_asset_id,
                duration_sim_seconds=spec.duration_sim_seconds,
                dt_seconds=spec.dt_seconds,
                run_start_time=spec.run_start_time,
                fault_start_sim_seconds=plan.fault_start_sim_seconds,
                fault_duration_sim_seconds=plan.fault_duration_sim_seconds,
                fault_severity=plan.fault_severity,
                operating_condition_ranges=spec.operating_condition_ranges,
                sensor_noise=spec.sensor_noise,
            )
            run_config = resolve_run_config(template)

            planned.append(
                PlannedRun(
                    simulation_run_id=run_id,
                    dataset_id=spec.dataset_id,
                    class_label=plan.scenario_name.value,
                    run_config=run_config,
                )
            )

    return tuple(planned)
