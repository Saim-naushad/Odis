"""Unit tests for scripts.benchmark_odis.statistics — no live services."""

from datetime import UTC, datetime, timedelta

from scripts.benchmark_odis.measurements import ResourceSample
from scripts.benchmark_odis.observers import InferenceResultObservation
from scripts.benchmark_odis.statistics import (
    LONGEST_WINDOW_SAMPLES,
    compute_throughput,
    latency_ms,
    percentile,
    steady_state_start,
    summarize_latencies,
    summarize_repeated_runs,
    summarize_resource_samples,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def test_longest_window_samples_matches_the_promoted_runtime_warmup() -> None:
    """Mirrors backend/simulator/dataset/features/config.py's
    LONGEST_WINDOW_SAMPLES (12 samples at the trained 10s cadence)."""
    assert LONGEST_WINDOW_SAMPLES == 12


def test_percentile_nearest_rank_on_five_values() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(values, 50) == 3.0
    assert percentile(values, 95) == 5.0
    assert percentile([], 95) == 0.0


def test_latency_ms_flags_negative_deltas_as_invalid() -> None:
    start = _T0
    end = _T0 - timedelta(milliseconds=5)
    sample = latency_ms(start, end)
    assert sample.valid is False


def test_latency_ms_accepts_zero_and_positive_deltas() -> None:
    assert latency_ms(_T0, _T0).valid is True
    assert latency_ms(_T0, _T0 + timedelta(milliseconds=1)).valid is True


def test_summarize_latencies_excludes_invalid_samples_from_percentiles() -> None:
    samples = [
        latency_ms(_T0, _T0 + timedelta(milliseconds=100)),
        latency_ms(_T0, _T0 + timedelta(milliseconds=200)),
        latency_ms(_T0, _T0 - timedelta(milliseconds=50)),  # invalid
    ]
    summary = summarize_latencies("test_metric", samples)
    assert summary.count == 2
    assert summary.excluded_count == 1
    assert summary.max_ms == 200.0


def test_summarize_latencies_handles_all_invalid() -> None:
    samples = [latency_ms(_T0, _T0 - timedelta(milliseconds=1))]
    summary = summarize_latencies("test_metric", samples)
    assert summary.count == 0
    assert summary.excluded_count == 1
    assert summary.median_ms == 0.0


def _inference_result(
    asset_id: str, sample_index: int, *, status: str = "valid_prediction"
) -> InferenceResultObservation:
    timestamp = _T0 + timedelta(seconds=10 * sample_index)
    return InferenceResultObservation(
        event_id=f"{asset_id}-{sample_index}",
        asset_id=asset_id,
        status=status,
        occurred_at=timestamp,
        source_timestamp=timestamp,
    )


def test_steady_state_start_is_none_until_every_asset_clears_warmup() -> None:
    results = [_inference_result("a", i) for i in range(1, 12)]  # only 11 samples
    assert steady_state_start(results, ("a", "b")) is None


def test_steady_state_start_is_max_over_assets_not_first_to_clear() -> None:
    results = [_inference_result("a", i) for i in range(1, 13)]  # a: 12 samples
    results += [_inference_result("b", i) for i in range(1, 20)]  # b: 19 samples
    boundary = steady_state_start(results, ("a", "b"))
    # asset "a"'s 12th sample is earlier than "b"'s 12th sample would be if
    # "b" started later — boundary must be the later of the two 12th samples.
    a_twelfth = _T0 + timedelta(seconds=10 * 12)
    b_twelfth = _T0 + timedelta(seconds=10 * 12)
    assert boundary == max(a_twelfth, b_twelfth)


def test_compute_throughput_distinguishes_valid_from_all_results() -> None:
    results = [_inference_result("a", i, status="warming_up") for i in range(1, 5)]
    results += [
        _inference_result("a", i, status="valid_prediction") for i in range(5, 15)
    ]
    throughput = compute_throughput(
        raw_telemetry_count=700,
        inference_results=results,
        window_seconds=100.0,
        steady_state=False,
    )
    assert throughput.telemetry_measurement_events_per_second == 7.0
    assert throughput.all_inference_results_per_second == 0.14
    assert throughput.valid_inference_results_per_second == 0.10
    # Currently identical by construction (one inference-result event per
    # assembled sample regardless of status) — see the module docstring.
    assert (
        throughput.complete_samples_per_second
        == throughput.all_inference_results_per_second
    )


def test_summarize_resource_samples_reports_avg_and_peak() -> None:
    samples = [
        ResourceSample(
            taken_at=0.0, container="c", cpu_percent=10.0, memory_bytes=100.0
        ),
        ResourceSample(
            taken_at=1.0, container="c", cpu_percent=30.0, memory_bytes=300.0
        ),
    ]
    summary = summarize_resource_samples("c", samples)
    assert summary is not None
    assert summary.sample_count == 2
    assert summary.avg_cpu_percent == 20.0
    assert summary.peak_cpu_percent == 30.0
    assert summary.peak_memory_bytes == 300.0


def test_summarize_resource_samples_returns_none_for_empty_input() -> None:
    assert summarize_resource_samples("c", []) is None


def test_summarize_repeated_runs_reports_median_and_range_not_the_best_run() -> None:
    summary = summarize_repeated_runs("metric", [10.0, 100.0, 20.0])
    assert summary.run_count == 3
    assert summary.median == 20.0
    assert summary.minimum == 10.0
    assert summary.maximum == 100.0
