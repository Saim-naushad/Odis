"""Deterministic, run-level, stratified train/validation/test splitting.

Splits are assigned to whole runs, never rows — a telemetry/ground-truth
row always inherits its run's split via `simulation_run_id`, so there is no
way for two rows of the same run to land in different splits.

Stratification key: `(class_label, target_asset_id)`. Splitting within
each stratum independently, at the same target proportions, preserves both
class balance and target-asset balance across splits "where practical" —
if a class/asset combination only has one or two runs, perfect three-way
balance isn't always possible, but the assignment stays deterministic and
documented rather than silently uneven.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from backend.simulator.dataset.dataset_spec import SplitProportions
from backend.simulator.dataset.run_plan import PlannedRun

_SPLIT_NAMES = ("train", "validation", "test")


@dataclass(frozen=True)
class SplitAssignment:
    """Disjoint run-id lists for one dataset, at one set of proportions."""

    dataset_id: str
    proportions: SplitProportions
    train: tuple[str, ...]
    validation: tuple[str, ...]
    test: tuple[str, ...]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "split_proportions": self.proportions.to_json_dict(),
            "train": list(self.train),
            "validation": list(self.validation),
            "test": list(self.test),
        }


def _split_counts(n: int, proportions: SplitProportions) -> tuple[int, int, int]:
    """Integer run counts per split for one stratum of size `n`.

    Largest-remainder apportionment: sums to exactly `n` regardless of
    rounding. Then, if `n` is large enough to give every split with a
    nonzero target proportion at least one run without emptying a larger
    split, moves runs one at a time to avoid a zero-count split — "each
    supported class is represented in each split when run counts permit."
    A split whose *target* proportion is exactly 0.0 is never forced to
    take a run — that would override an explicit "no test data" choice.
    """
    if n == 0:
        return 0, 0, 0

    props = (proportions.train, proportions.validation, proportions.test)
    raw = [p * n for p in props]
    counts = [int(r) for r in raw]
    remainder = n - sum(counts)
    order = sorted(range(3), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[:remainder]:
        counts[i] += 1

    nonzero_splits = sum(1 for p in props if p > 0)
    if n >= nonzero_splits:
        for i in range(3):
            if props[i] > 0 and counts[i] == 0:
                donor = max(range(3), key=lambda j: counts[j])
                if counts[donor] > 1:
                    counts[donor] -= 1
                    counts[i] += 1

    return counts[0], counts[1], counts[2]


def assign_splits(
    planned_runs: tuple[PlannedRun, ...],
    proportions: SplitProportions,
    *,
    dataset_id: str,
) -> SplitAssignment:
    """Deterministically assign every planned run to exactly one split.

    Shuffling within a stratum uses `random.Random(f"{dataset_id}:{stratum}")`
    — deterministic given `dataset_id`, isolated from every other RNG
    stream in this package (operating conditions, sensor noise), and never
    touches Python's global random state.
    """
    strata: dict[tuple[str, str], list[str]] = {}
    for run in planned_runs:
        key = (run.class_label, run.run_config.target_asset_id)
        strata.setdefault(key, []).append(run.simulation_run_id)

    train: list[str] = []
    validation: list[str] = []
    test: list[str] = []

    for class_label, target_asset_id in sorted(strata):
        run_ids = sorted(strata[(class_label, target_asset_id)])
        rng = random.Random(f"{dataset_id}:split:{class_label}:{target_asset_id}")
        rng.shuffle(run_ids)

        n_train, n_val, _n_test = _split_counts(len(run_ids), proportions)
        train.extend(run_ids[:n_train])
        validation.extend(run_ids[n_train : n_train + n_val])
        test.extend(run_ids[n_train + n_val :])

    return SplitAssignment(
        dataset_id=dataset_id,
        proportions=proportions,
        train=tuple(train),
        validation=tuple(validation),
        test=tuple(test),
    )
