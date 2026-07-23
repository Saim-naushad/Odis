# PR181 technical performance benchmark

`scripts/benchmark_odis` measures the end-to-end performance, scale
behavior, reliability, and resource usage of the ODIS v1.1 pipeline
(`Plant Alpha → Kafka → fault-inference worker → temporal alert policy →
reasoning-bridge worker → Postgres/outbox → Redis/SSE → dashboard`) using
reproducible local scenarios. It measures the existing system; it adds no
new reasoning, detector, or model logic.

All results are **local-machine measurements** — never cloud or production
hardware, never extrapolated capacity claims.

## Why a new tool, and why so little of it is new instrumentation

An audit (recorded in the PR181 planning discussion) found that almost
every measurement this benchmark needs already exists in the codebase:

- The simulator already supports scaling to an arbitrary asset count
  (`PlantAlphaFleet.create()` falls back to a default baseline for any
  asset id it doesn't recognize) and already decouples simulated time from
  wall-clock publish pacing (`kafka_sample_interval_seconds` vs.
  `kafka_publish_interval_seconds`) — the same acceleration the demo
  profile already uses for its ~9x speed-up.
- Every latency hop's endpoints already exist as fields on existing Kafka
  events or DB columns (`source_timestamp`/`occurred_at` on
  `fault_inference.v1`/`fault_alert_transition.v1`; `observed_at`/
  `recorded_at` on `ai_fault_evidence`) — verified directly against
  `_publish_kafka_snapshot` (`backend/simulator/__main__.py`) to confirm
  `source_timestamp` is real wall-clock acquisition time, not a simulated
  clock.
- Reliability mechanisms (deterministic event-id dedup, DB-unique-constraint
  idempotency, at-least-once with manual offset commit, outbox retry) are
  all already implemented; the benchmark verifies them, it doesn't add them.

So this tool is almost entirely **orchestration and measurement
correlation**, not new instrumentation. The one genuinely new thing is
observing external visibility (API polling, SSE receipt) — no existing
metric can substitute for "did an external client actually see it."

## Architecture

```
scripts/benchmark_odis/
  config.py           RunConfig, validation, environment.json capture
  stack.py            ephemeral Compose lifecycle, port preflight
  simulator_driver.py  host-side `python -m backend.simulator` subprocess
  observers.py         Kafka observer + SSE client + API poller (live)
  measurements.py       Postgres queries, consumer lag, docker stats (pull)
  statistics.py         percentiles, warm-up exclusion, throughput, resource reduction
  reliability.py        --mode reliability checks (separate from performance)
  report.py             artifact writing + resume-safe claim generation
  __main__.py           CLI + orchestration
```

Each benchmark run gets its own ephemeral Docker Compose project
(`odis-benchmark-<run-id>`, `docker-compose.yml` + `docker-compose.benchmark.yml`,
which maps Postgres/Kafka/Redis/Prometheus to non-default host ports so a
run can never collide with an already-running dev/demo stack). All host
ports are pre-flight-checked as free *before* any container is created —
never a partial start. The simulator itself runs as a host subprocess
(not a container) so asset count/scenario/cadence can vary per run without
a rebuild. Fresh project + volumes per repetition is the default isolation
mechanism: it structurally rules out cross-repetition contamination
(accumulated observations, lingering open investigations, retained Kafka
messages/offsets, carried-over Prometheus counters) rather than filtering
it out after the fact.

`--mode performance` (default) never injects failures. `--mode reliability`
is a completely separate run, on its own ephemeral stack, that verifies
replay idempotency, malformed-input handling, and outage/retry behavior —
kept apart so injected failures can never contaminate latency/throughput
numbers.

## Measurement contracts

| Metric | Definition | Time domain |
|---|---|---|
| `telemetry_acquisition_to_inference_publish_ms` | `fault_inference.v1.occurred_at - source_timestamp`, exact per-event | wall-clock |
| `fault_onset_to_confirmation_sim_seconds` | `(confirmation_sample_index - fault_onset_sample_index) * kafka_sample_interval_seconds` | simulated (sample-count based) |
| `alert_publish_to_reasoning_persist_ms` | `ai_fault_evidence.recorded_at - fault_alert_transition.v1.occurred_at`, joined via `source_event_id` | wall-clock |
| `source_sample_to_durable_reasoning_record_ms` | `ai_fault_evidence.recorded_at - observed_at` (informational — spans back to the original sample, not the confirmed transition) | wall-clock |
| `reasoning_persist_to_api_observed_ms` | API poller first-success receipt − `recorded_at`; bounded by the poll interval | wall-clock, observer-measured |
| `reasoning_persist_to_sse_observed_ms` | SSE client first-receipt − `recorded_at`; observer receive latency (Redis + API process + network), not browser-render latency | wall-clock, observer-measured |
| `scenario_start_to_recommendation_ms` | subprocess-launch T0 → first recommendation visible — "demo elapsed time," not a fault-response metric | wall-clock |
| `fault_onset_to_recommendation_wall_ms` | headline fault-response metric — see onset derivation below | wall-clock |

### Fault onset is sample index 2, not sample index 1

`CoolingDegradationScenario.tick()` runs the baseline physics tick
*before* updating the cooling-efficiency target for the next tick, so
sample index 1's published telemetry is provably identical to a healthy
fleet's — the ramp is only observable from sample index 2 onward. This is
pinned by `tests/backend/simulator/test_scenarios.py::
test_cooling_degradation_onset_lands_on_second_sample`, which drives a
`CoolingDegradationScenario` fleet and a control fleet in lockstep and
asserts the divergence point directly from the scenario's own code, so a
future reordering fails the test instead of silently shifting the
benchmark's onset definition.

### Negative latencies are measurement errors, not zero

Any computed latency that comes out negative (clock precision, ordering, a
polling race) is recorded as an excluded/invalid sample, never silently
clamped to zero — `statistics.LatencySummary.excluded_count` reports how
many were dropped.

### Single host clock

Every container and the benchmark's own observer/poller process share one
host clock in this single-machine setup — there is no cross-host NTP-skew
concern to account for.

## Usage

```bash
# Scenario A (healthy throughput), 10 assets, 5 minutes
python -m scripts.benchmark_odis --scenario normal_operation --assets 10 --duration 300

# Scenario B (canonical fault lifecycle), 1 asset
python -m scripts.benchmark_odis --scenario cooling_degradation --assets 1 --duration 300

# Reliability mode (separate stack, never mixed with performance numbers)
python -m scripts.benchmark_odis --mode reliability --scenario cooling_degradation --duration 180
```

`--scenario cooling_degradation` always requires `--transport kafka+http`
(the default) — the reasoning-bridge's corroboration reads persisted
`Observation` rows, not Kafka messages, so a Kafka-only run would leave
reasoning with no observation history to corroborate against.

Outputs land under `benchmark-results/<run-id>/` (gitignored):
`config.json`, `environment.json`, `raw-metrics.json`, `summary.json`,
`report.md`. The consolidated, cross-run report lives at
`docs/release/v1.1-performance-report.md`.

## Tests

Unit tests (`tests/scripts/test_benchmark_odis_*.py`) cover config
validation, deterministic run-id generation, percentile/warm-up-exclusion
math, and reconciliation — no live stack required. A `benchmark`-marked
integration test (`tests/integration/test_benchmark_odis_smoke.py`, skipped
by default) exercises the real orchestration path against a live ephemeral
stack.
