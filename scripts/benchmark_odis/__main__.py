"""PR181 benchmark CLI entry point.

Usage:
    python -m scripts.benchmark_odis --assets 10 --scenario cooling_degradation \\
        --duration 300 --publish-interval 1.1 --output-dir benchmark-results

    python -m scripts.benchmark_odis --mode reliability --output-dir benchmark-results

See docs/benchmarking.md for the full architecture and measurement
contracts; this module is intentionally thin orchestration — the actual
logic lives in `config.py`, `stack.py`, `simulator_driver.py`,
`observers.py`, `measurements.py`, `statistics.py`, `reliability.py`, and
`report.py`.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from scripts.benchmark_odis import measurements as m
from scripts.benchmark_odis import observers as obs
from scripts.benchmark_odis import reliability as rel
from scripts.benchmark_odis import report
from scripts.benchmark_odis import statistics as stats
from scripts.benchmark_odis.config import (
    ConfigError,
    RunConfig,
    capture_environment,
    make_run_id,
    validate_config,
)
from scripts.benchmark_odis.simulator_driver import SimulatorProcess
from scripts.benchmark_odis.stack import BenchmarkStack

# fault_onset is sample index 2 for CoolingDegradationScenario — pinned by
# tests/backend/simulator/test_scenarios.py::
# test_cooling_degradation_onset_lands_on_second_sample. Never sample index
# 1, subprocess start time, or first confirmed diagnosis.
FAULT_ONSET_SAMPLE_INDEX = 2
FAULT_TARGET_ASSET = "fuel-cell-stack-01"
API_POLL_INTERVAL_SECONDS = 2.0
DRAIN_SECONDS = 15.0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=int, default=1)
    parser.add_argument(
        "--scenario",
        default="cooling_degradation",
        choices=("normal_operation", "cooling_degradation"),
    )
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--publish-interval", type=float, default=1.1)
    parser.add_argument("--sample-interval", type=float, default=10.0)
    parser.add_argument("--transport", default="kafka+http")
    parser.add_argument("--output-dir", default="benchmark-results")
    parser.add_argument(
        "--mode", default="performance", choices=("performance", "reliability")
    )
    parser.add_argument("--repetition-index", type=int, default=0)
    parser.add_argument("--keep-stack", action="store_true")
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> RunConfig:
    run_id = make_run_id(
        scenario=args.scenario,
        asset_count=args.assets,
        repetition_index=args.repetition_index,
        now=datetime.now(UTC),
    )
    return RunConfig(
        run_id=run_id,
        mode=args.mode,
        scenario=args.scenario,
        asset_count=args.assets,
        duration_seconds=args.duration,
        kafka_publish_interval_seconds=args.publish_interval,
        kafka_sample_interval_seconds=args.sample_interval,
        transport=args.transport,
        output_dir=Path(args.output_dir),
        repetition_index=args.repetition_index,
        keep_stack=args.keep_stack,
    )


def run_performance(config: RunConfig) -> int:
    environment = capture_environment(config)
    stack = BenchmarkStack(config)
    stack.up()

    project_name = config.compose_project_name()
    asset_ids = config.asset_ids()
    resource_containers = tuple(
        f"{project_name}-{service}-1"
        for service in (
            "api",
            "worker",
            "reasoning-bridge-worker",
            "fault-inference-worker",
        )
    )

    sse_observer = obs.SseObserver(api_base_url=stack.endpoints.api_base_url)
    sse_observer.start()
    sse_subscribed = sse_observer.wait_subscribed(timeout_seconds=20.0)

    kafka_observer = obs.KafkaObserver(
        bootstrap_servers=stack.endpoints.kafka_bootstrap_servers,
        group_id=f"odis-benchmark-observer-{config.run_id}",
    )
    kafka_observer.start()

    resource_sampler = m.DockerStatsSampler(containers=resource_containers)
    resource_sampler.start()

    api_poller = obs.ApiPoller(
        api_base_url=stack.endpoints.api_base_url,
        poll_interval_seconds=API_POLL_INTERVAL_SECONDS,
    )

    sim = SimulatorProcess(config, stack.endpoints, run_id=config.run_id)
    sim.start()

    try:
        deadline = time.monotonic() + config.duration_seconds
        while time.monotonic() < deadline:
            for asset_id in asset_ids:
                # A poll failure must not abort the run.
                with contextlib.suppress(Exception):
                    api_poller.poll_once(asset_id)
            time.sleep(API_POLL_INTERVAL_SECONDS)
        time.sleep(DRAIN_SECONDS)
    finally:
        sim.stop()
        resource_sampler.stop()
        kafka_observer.stop()
        sse_observer.stop()
        api_poller.close()

    from backend.app.infrastructure.config.settings import Settings
    from backend.app.infrastructure.database.session import (
        create_db_engine,
        create_session_factory,
    )

    settings = Settings(database_url=stack.endpoints.database_url)
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        evidence_rows = m.query_ai_fault_evidence(session, asset_ids)
        counts = m.reconcile_counts(session, asset_ids)

    lag = m.consumer_lag(
        bootstrap_servers=stack.endpoints.kafka_bootstrap_servers,
        group_id=m.FAULT_INFERENCE_CONSUMER_GROUP,
        topics=(obs.TELEMETRY_TOPIC,),
    ) | m.consumer_lag(
        bootstrap_servers=stack.endpoints.kafka_bootstrap_servers,
        group_id=m.REASONING_BRIDGE_CONSUMER_GROUP,
        topics=(obs.ALERT_TRANSITIONS_TOPIC,),
    )

    summary = _summarize(
        config=config,
        asset_ids=asset_ids,
        kafka_observer=kafka_observer,
        sse_observer=sse_observer,
        sse_subscribed=sse_subscribed,
        api_poller=api_poller,
        evidence_rows=evidence_rows,
        counts=counts,
        consumer_lag=lag,
        resource_sampler=resource_sampler,
        resource_containers=resource_containers,
        run_duration_seconds=config.duration_seconds,
    )

    raw_metrics = {
        "inference_result_count": len(kafka_observer.inference_results),
        "alert_transition_count": len(kafka_observer.alert_transitions),
        "reasoning_results_count": kafka_observer.reasoning_results_count,
        "raw_telemetry_count": kafka_observer.raw_telemetry_count,
        "raw_telemetry_count_by_asset": dict(
            kafka_observer.raw_telemetry_count_by_asset
        ),
    }

    engine.dispose()

    run_dir = config.run_dir()
    report.write_run_artifacts(
        run_dir,
        config=_config_as_dict(config),
        environment=environment,
        raw_metrics=raw_metrics,
        summary=summary,
    )
    print(f"wrote {run_dir}")

    if not config.keep_stack:
        stack.down()
    return 0


def _config_as_dict(config: RunConfig) -> dict[str, object]:
    return {
        "run_id": config.run_id,
        "mode": config.mode,
        "scenario": config.scenario,
        "asset_count": config.asset_count,
        "duration_seconds": config.duration_seconds,
        "kafka_publish_interval_seconds": config.kafka_publish_interval_seconds,
        "kafka_sample_interval_seconds": config.kafka_sample_interval_seconds,
        "transport": config.transport,
        "repetition_index": config.repetition_index,
        "asset_ids": list(config.asset_ids()),
    }


def _summarize(
    *,
    config: RunConfig,
    asset_ids: tuple[str, ...],
    kafka_observer: obs.KafkaObserver,
    sse_observer: obs.SseObserver,
    sse_subscribed: bool,
    api_poller: obs.ApiPoller,
    evidence_rows: list[m.AiFaultEvidenceRow],
    counts: m.ReconciliationCounts,
    consumer_lag: dict[str, int],
    resource_sampler: m.DockerStatsSampler,
    resource_containers: tuple[str, ...],
    run_duration_seconds: float,
) -> dict[str, object]:
    hop1_samples = [
        stats.latency_ms(r.source_timestamp, r.occurred_at)
        for r in kafka_observer.inference_results
    ]
    hop1 = stats.summarize_latencies(
        "telemetry_acquisition_to_inference_publish_ms", hop1_samples
    )

    evidence_by_source_event_id = {row.source_event_id: row for row in evidence_rows}
    hop3_samples = []
    source_sample_to_reasoning_samples = []
    for transition in kafka_observer.alert_transitions:
        row = evidence_by_source_event_id.get(transition.event_id)
        if row is None:
            continue
        hop3_samples.append(stats.latency_ms(transition.occurred_at, row.recorded_at))
        source_sample_to_reasoning_samples.append(
            stats.latency_ms(row.observed_at, row.recorded_at)
        )
    hop3 = stats.summarize_latencies(
        "alert_publish_to_reasoning_persist_ms", hop3_samples
    )
    source_sample_to_reasoning = stats.summarize_latencies(
        "source_sample_to_durable_reasoning_record_ms",
        source_sample_to_reasoning_samples,
    )

    hop4_samples = []
    hop5_samples = []
    for row in evidence_rows:
        # `_after` variants match each row to its *own* subsequent
        # visibility, not the asset's first-ever visibility — an asset with
        # multiple evidence rows (e.g. a class_changed update) would
        # otherwise have later rows compared against an earlier row's
        # observation, producing negative (and correctly excluded, but
        # avoidable) latencies.
        first_api = api_poller.first_visible_after(row.asset_id, row.recorded_at)
        if first_api is not None:
            hop4_samples.append(
                stats.latency_ms(row.recorded_at, first_api.received_at)
            )
        first_sse = sse_observer.first_event_for_asset_after(
            row.asset_id, row.recorded_at
        )
        if first_sse is not None:
            hop5_samples.append(
                stats.latency_ms(row.recorded_at, first_sse.received_at)
            )
    hop4 = stats.summarize_latencies(
        "reasoning_persist_to_api_observed_ms", hop4_samples
    )
    hop5 = stats.summarize_latencies(
        "reasoning_persist_to_sse_observed_ms", hop5_samples
    )

    onset_source_timestamp = None
    fault_onset_to_confirmation_sim_seconds = None
    fault_onset_to_recommendation_wall_ms = None
    if config.scenario == "cooling_degradation":
        ordered = kafka_observer.inference_results_for_asset(FAULT_TARGET_ASSET)
        if len(ordered) >= FAULT_ONSET_SAMPLE_INDEX:
            onset = ordered[FAULT_ONSET_SAMPLE_INDEX - 1]
            onset_source_timestamp = onset.source_timestamp
            confirmation = kafka_observer.first_confirmed_transition(FAULT_TARGET_ASSET)
            if confirmation is not None:
                confirmation_index = kafka_observer.sample_index_for_asset(
                    FAULT_TARGET_ASSET, confirmation.source_timestamp
                )
                if confirmation_index is not None:
                    fault_onset_to_confirmation_sim_seconds = (
                        confirmation_index - FAULT_ONSET_SAMPLE_INDEX
                    ) * config.kafka_sample_interval_seconds
            recommendation_visible = api_poller.first_with_recommendation(
                FAULT_TARGET_ASSET
            )
            if recommendation_visible is not None:
                sample = stats.latency_ms(
                    onset.source_timestamp, recommendation_visible.received_at
                )
                fault_onset_to_recommendation_wall_ms = {
                    "milliseconds": sample.milliseconds,
                    "valid": sample.valid,
                }

    steady_state_boundary = stats.steady_state_start(
        kafka_observer.inference_results, asset_ids
    )
    throughput_including_warmup = stats.compute_throughput(
        raw_telemetry_count=kafka_observer.raw_telemetry_count,
        inference_results=kafka_observer.inference_results,
        window_seconds=run_duration_seconds,
        steady_state=False,
    )

    resource_summaries = {
        container: stats.summarize_resource_samples(
            container, resource_sampler.samples_for(container)
        )
        for container in resource_containers
    }

    return {
        "hop_latencies": {
            "telemetry_acquisition_to_inference_publish_ms": hop1.__dict__,
            "alert_publish_to_reasoning_persist_ms": hop3.__dict__,
            "source_sample_to_durable_reasoning_record_ms": (
                source_sample_to_reasoning.__dict__
            ),
            "reasoning_persist_to_api_observed_ms": hop4.__dict__,
            "reasoning_persist_to_sse_observed_ms": hop5.__dict__,
            "fault_onset_to_confirmation_sim_seconds": (
                fault_onset_to_confirmation_sim_seconds
            ),
            "fault_onset_to_recommendation_wall_ms": (
                fault_onset_to_recommendation_wall_ms
            ),
        },
        "onset": {
            "fault_onset_sample_index": FAULT_ONSET_SAMPLE_INDEX,
            "fault_onset_source_timestamp": onset_source_timestamp,
            "target_asset": FAULT_TARGET_ASSET,
        },
        "throughput_including_warmup": throughput_including_warmup.__dict__,
        "steady_state_boundary": steady_state_boundary,
        "reconciliation": counts.__dict__,
        "consumer_lag_at_end": consumer_lag,
        "resource_usage": {
            k: (v.__dict__ if v is not None else None)
            for k, v in resource_summaries.items()
        },
        "observability": {
            "api_poll_interval_seconds": API_POLL_INTERVAL_SECONDS,
            "sse_connection_established_at": sse_observer.connection_established_at,
            "sse_subscribed_before_simulator_launch": sse_subscribed,
            "malformed_kafka_messages_observed": kafka_observer.malformed_message_count,
        },
        "total_telemetry_events": kafka_observer.raw_telemetry_count,
        "max_stable_asset_count": len(asset_ids),
    }


def run_reliability(config: RunConfig) -> int:
    environment = capture_environment(config)
    stack = BenchmarkStack(config)
    stack.up()
    project_name = config.compose_project_name()

    kafka_observer = obs.KafkaObserver(
        bootstrap_servers=stack.endpoints.kafka_bootstrap_servers,
        group_id=f"odis-benchmark-observer-{config.run_id}",
    )
    kafka_observer.start()

    sim = SimulatorProcess(config, stack.endpoints, run_id=config.run_id)
    sim.start()
    time.sleep(config.duration_seconds)
    sim.stop()
    time.sleep(DRAIN_SECONDS)
    kafka_observer.stop()

    from backend.app.infrastructure.config.settings import Settings
    from backend.app.infrastructure.database.session import (
        create_db_engine,
        create_session_factory,
    )

    settings = Settings(database_url=stack.endpoints.database_url)
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    captured = kafka_observer.alert_transitions[:2]
    replay_result = None
    if captured:
        import json as _json

        with session_factory() as session:
            replay_result = rel.replay_alert_transitions(
                bootstrap_servers=stack.endpoints.kafka_bootstrap_servers,
                topic=obs.ALERT_TRANSITIONS_TOPIC,
                captured_messages=[
                    _json.dumps(
                        {
                            "event_id": t.event_id,
                            "event_version": "v1",
                            "occurred_at": t.occurred_at.isoformat(),
                            "asset_id": t.asset_id,
                            "source_timestamp": t.source_timestamp.isoformat(),
                            "transition_type": t.transition_type,
                        }
                    ).encode("utf-8")
                    for t in captured
                ],
                captured_keys=[t.asset_id.encode("utf-8") for t in captured],
                session=session,
                asset_ids=config.asset_ids(),
            )

    rel.publish_malformed_telemetry(
        bootstrap_servers=stack.endpoints.kafka_bootstrap_servers,
        topic=obs.TELEMETRY_TOPIC,
    )
    time.sleep(5.0)
    malformed_metric = rel.query_prometheus_scalar(
        prometheus_base_url=stack.endpoints.prometheus_base_url,
        promql='sum(fault_inference_malformed_events_total)',
    )
    worker_running = rel.container_is_running(project_name, "fault-inference-worker")

    outbox_result = rel.outbox_kafka_leg_recovery_check(
        session_factory=session_factory, project_name=project_name
    )
    ai_durability_result = rel.ai_investigation_durability_check(
        session_factory=session_factory,
        project_name=project_name,
        redis_url=stack.endpoints.redis_url,
    )

    engine.dispose()

    summary = {
        "replay_idempotency": replay_result.__dict__ if replay_result else None,
        "malformed_telemetry_counter_total": malformed_metric,
        "fault_inference_worker_still_running": worker_running,
        "outbox_kafka_leg_recovery": outbox_result.__dict__,
        "ai_investigation_durability": ai_durability_result.__dict__,
    }

    run_dir = config.run_dir()
    report.write_run_artifacts(
        run_dir,
        config=_config_as_dict(config),
        environment=environment,
        raw_metrics={},
        summary=summary,
    )
    print(f"wrote {run_dir}")

    if not config.keep_stack:
        stack.down()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    config = build_config(args)
    try:
        validate_config(config)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if config.mode == "reliability":
        return run_reliability(config)
    return run_performance(config)


if __name__ == "__main__":
    sys.exit(main())
