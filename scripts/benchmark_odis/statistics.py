"""Percentiles, warm-up exclusion, throughput, and resource reduction (PR181).

Percentile method: nearest-rank over the exact set of directly observed
samples (`rank = round((pct / 100) * (n - 1))`, no interpolation) — the same
method `scripts/benchmark_reasoning_worker.py._percentile` already uses, kept
consistent here. This is a genuine order-statistic over observed samples,
distinct from the Prometheus histograms' bucket-interpolated
`histogram_quantile`, which this module never uses for latency computed from
directly-observed events.
"""

from __future__ import annotations

import statistics as stdlib_statistics
from dataclasses import dataclass
from datetime import datetime

from scripts.benchmark_odis.measurements import ResourceSample
from scripts.benchmark_odis.observers import InferenceResultObservation

# Mirrors `backend/simulator/dataset/features/config.py`'s
# `LONGEST_WINDOW_SAMPLES` (12 samples at the promoted runtime's trained 10s
# cadence). Duplicated rather than imported for the same reason
# `backend/simulator/config.py` duplicates it: importing
# `backend.simulator.dataset.features` unconditionally pulls in its
# pyarrow-dependent `generate` submodule at package-init time.
# `tests/backend/simulator/test_kafka_sample_synchronization.py::
# test_default_kafka_sample_interval_matches_trained_cadence` is the existing
# test that would catch this drifting; this module's own unit test asserts
# the same value.
LONGEST_WINDOW_SAMPLES = 12


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1))))
    return ordered[rank]


@dataclass(frozen=True)
class LatencySample:
    milliseconds: float
    valid: bool


def latency_ms(start: datetime, end: datetime) -> LatencySample:
    """A negative delta (clock precision, ordering, or a polling race) is
    flagged invalid rather than silently clamped to zero — callers exclude
    invalid samples from percentiles and report the exclusion count."""
    delta_ms = (end - start).total_seconds() * 1000.0
    return LatencySample(milliseconds=delta_ms, valid=delta_ms >= 0.0)


@dataclass(frozen=True)
class LatencySummary:
    metric_name: str
    count: int
    excluded_count: int
    median_ms: float
    p95_ms: float
    max_ms: float


def summarize_latencies(
    metric_name: str, samples: list[LatencySample]
) -> LatencySummary:
    valid = [s.milliseconds for s in samples if s.valid]
    return LatencySummary(
        metric_name=metric_name,
        count=len(valid),
        excluded_count=len(samples) - len(valid),
        median_ms=percentile(valid, 50),
        p95_ms=percentile(valid, 95),
        max_ms=max(valid) if valid else 0.0,
    )


def steady_state_start(
    inference_results: list[InferenceResultObservation],
    asset_ids: tuple[str, ...],
) -> datetime | None:
    """The wall-clock timestamp at which *every* asset has cleared warm-up —
    `max` over assets of that asset's own `LONGEST_WINDOW_SAMPLES`-th sample,
    never the first asset to cross the threshold. Returns `None` if any
    asset hasn't cleared warm-up yet (steady-state hasn't begun)."""
    boundaries: list[datetime] = []
    for asset_id in asset_ids:
        ordered = sorted(
            (r for r in inference_results if r.asset_id == asset_id),
            key=lambda r: r.source_timestamp,
        )
        if len(ordered) < LONGEST_WINDOW_SAMPLES:
            return None
        boundaries.append(ordered[LONGEST_WINDOW_SAMPLES - 1].source_timestamp)
    return max(boundaries) if boundaries else None


@dataclass(frozen=True)
class ThroughputSummary:
    telemetry_measurement_events_per_second: float
    complete_samples_per_second: float
    valid_inference_results_per_second: float
    all_inference_results_per_second: float
    measurement_window_seconds: float
    steady_state: bool


def compute_throughput(
    *,
    raw_telemetry_count: int,
    inference_results: list[InferenceResultObservation],
    window_seconds: float,
    steady_state: bool,
) -> ThroughputSummary:
    """The four throughput denominators are kept distinct even though
    `complete_samples_per_second` and `all_inference_results_per_second`
    are currently numerically identical by construction (every assembled
    sample yields exactly one `fault_inference.v1` event regardless of
    status — see `inference_worker/events.py`'s docstring) — they measure
    different concepts and would diverge if that 1:1 relationship ever
    changed (e.g. batched publishing)."""
    if window_seconds <= 0:
        msg = f"window_seconds must be positive, got {window_seconds}"
        raise ValueError(msg)
    valid_count = sum(
        1 for r in inference_results if r.status == "valid_prediction"
    )
    all_count = len(inference_results)
    return ThroughputSummary(
        telemetry_measurement_events_per_second=raw_telemetry_count / window_seconds,
        complete_samples_per_second=all_count / window_seconds,
        valid_inference_results_per_second=valid_count / window_seconds,
        all_inference_results_per_second=all_count / window_seconds,
        measurement_window_seconds=window_seconds,
        steady_state=steady_state,
    )


@dataclass(frozen=True)
class ResourceSummary:
    container: str
    sample_count: int
    avg_cpu_percent: float
    peak_cpu_percent: float
    avg_memory_bytes: float
    peak_memory_bytes: float


def summarize_resource_samples(
    container: str, samples: list[ResourceSample]
) -> ResourceSummary | None:
    """Docker's CPU% is relative to a single core (100% == one full core
    saturated; multi-threaded containers on a multi-core host can exceed
    100%) — `report.py` states this alongside every resource table."""
    if not samples:
        return None
    cpu_values = [s.cpu_percent for s in samples]
    memory_values = [s.memory_bytes for s in samples]
    return ResourceSummary(
        container=container,
        sample_count=len(samples),
        avg_cpu_percent=stdlib_statistics.mean(cpu_values),
        peak_cpu_percent=max(cpu_values),
        avg_memory_bytes=stdlib_statistics.mean(memory_values),
        peak_memory_bytes=max(memory_values),
    )


@dataclass(frozen=True)
class RepeatedRunSummary:
    metric_name: str
    run_count: int
    median: float
    minimum: float
    maximum: float


def summarize_repeated_runs(
    metric_name: str, values: list[float]
) -> RepeatedRunSummary:
    """Median + range across repetitions — never the best run cherry-picked."""
    if not values:
        return RepeatedRunSummary(
            metric_name=metric_name, run_count=0, median=0.0, minimum=0.0, maximum=0.0
        )
    return RepeatedRunSummary(
        metric_name=metric_name,
        run_count=len(values),
        median=stdlib_statistics.median(values),
        minimum=min(values),
        maximum=max(values),
    )
