# Benchmark run 20260723052900-cooling-degradation-100a-r0

Mode: `performance` · Scenario: `cooling_degradation` · Assets: 100 · Duration: 380.0s

Local-machine measurement only — not a production or cloud result.

## Environment

- **git_commit**: b006027d55d0f4907a37f864578a3c1ddfb22f29
- **os**: Darwin
- **cpu_architecture**: arm64
- **cpu_model**: Apple M2
- **cpu_count**: 8
- **memory_bytes**: 17179869184
- **docker_version**: Docker version 28.4.0, build d8eb465
- **python_version**: 3.11.8
- **model**: {'system_version': 'plant_alpha_fault_v1', 'model_hash': '30ae2bad5eca428b78e72756c49e71f89c0db8584b79ce3fef7790d7d6067a8f', 'policy_hash': 'e266aad024c8db0e4ced2e486c371b704df23fc5973954b2a17a948b5db22809', 'feature_schema_version': '1.0'}
- **benchmark_timestamp**: 2026-07-23T05:29:00.728797+00:00

## Summary

```json
{
  "hop_latencies": {
    "telemetry_acquisition_to_inference_publish_ms": {
      "metric_name": "telemetry_acquisition_to_inference_publish_ms",
      "count": 3460,
      "excluded_count": 0,
      "median_ms": 5617.8369999999995,
      "p95_ms": 11556.348,
      "max_ms": 16410.864
    },
    "alert_publish_to_reasoning_persist_ms": {
      "metric_name": "alert_publish_to_reasoning_persist_ms",
      "count": 5,
      "excluded_count": 0,
      "median_ms": 38.582,
      "p95_ms": 209.155,
      "max_ms": 209.155
    },
    "source_sample_to_durable_reasoning_record_ms": {
      "metric_name": "source_sample_to_durable_reasoning_record_ms",
      "count": 5,
      "excluded_count": 0,
      "median_ms": 2400.652,
      "p95_ms": 2643.982,
      "max_ms": 2643.982
    },
    "reasoning_persist_to_api_observed_ms": {
      "metric_name": "reasoning_persist_to_api_observed_ms",
      "count": 4,
      "excluded_count": 0,
      "median_ms": 1060.683,
      "p95_ms": 1499.236,
      "max_ms": 1499.236
    },
    "reasoning_persist_to_sse_observed_ms": {
      "metric_name": "reasoning_persist_to_sse_observed_ms",
      "count": 5,
      "excluded_count": 0,
      "median_ms": 19.657,
      "p95_ms": 34.986000000000004,
      "max_ms": 34.986000000000004
    },
    "fault_onset_to_confirmation_sim_seconds": 330.0,
    "fault_onset_to_recommendation_wall_ms": null
  },
  "onset": {
    "fault_onset_sample_index": 2,
    "fault_onset_source_timestamp": "2026-07-23 05:29:31.484203+00:00",
    "target_asset": "fuel-cell-stack-01"
  },
  "throughput_including_warmup": {
    "telemetry_measurement_events_per_second": 72.84210526315789,
    "complete_samples_per_second": 9.105263157894736,
    "valid_inference_results_per_second": 6.2105263157894735,
    "all_inference_results_per_second": 9.105263157894736,
    "measurement_window_seconds": 380.0,
    "steady_state": false
  },
  "steady_state_boundary": "2026-07-23 05:31:36.466429+00:00",
  "reconciliation": {
    "observation_rows": 27678,
    "timeline_event_rows": 40138,
    "ai_fault_evidence_rows": 5,
    "outbox_pending_rows": 0,
    "distinct_investigation_ids": 5
  },
  "consumer_lag_at_end": {
    "odis.telemetry.observations.v1": 0,
    "odis.fault.alert-transitions.v1": 0
  },
  "resource_usage": {
    "odis-benchmark-20260723052900-cooling-degradation-100a-r0-api-1": {
      "container": "odis-benchmark-20260723052900-cooling-degradation-100a-r0-api-1",
      "sample_count": 45,
      "avg_cpu_percent": 62.77622222222222,
      "peak_cpu_percent": 128.9,
      "avg_memory_bytes": 112815825.80622222,
      "peak_memory_bytes": 124465971.2
    },
    "odis-benchmark-20260723052900-cooling-degradation-100a-r0-worker-1": {
      "container": "odis-benchmark-20260723052900-cooling-degradation-100a-r0-worker-1",
      "sample_count": 45,
      "avg_cpu_percent": 82.31911111111111,
      "peak_cpu_percent": 110.65,
      "avg_memory_bytes": 102053241.74222222,
      "peak_memory_bytes": 130442854.4
    },
    "odis-benchmark-20260723052900-cooling-degradation-100a-r0-reasoning-bridge-worker-1": {
      "container": "odis-benchmark-20260723052900-cooling-degradation-100a-r0-reasoning-bridge-worker-1",
      "sample_count": 45,
      "avg_cpu_percent": 0.998,
      "peak_cpu_percent": 5.04,
      "avg_memory_bytes": 75458791.19644444,
      "peak_memory_bytes": 77133250.56
    },
    "odis-benchmark-20260723052900-cooling-degradation-100a-r0-fault-inference-worker-1": {
      "container": "odis-benchmark-20260723052900-cooling-degradation-100a-r0-fault-inference-worker-1",
      "sample_count": 45,
      "avg_cpu_percent": 10.893333333333333,
      "peak_cpu_percent": 15.11,
      "avg_memory_bytes": 115378312.53333333,
      "peak_memory_bytes": 115867648.0
    }
  },
  "observability": {
    "api_poll_interval_seconds": 2.0,
    "sse_connection_established_at": "2026-07-23 10:29:21.831954+05:00",
    "sse_subscribed_before_simulator_launch": true,
    "malformed_kafka_messages_observed": 0
  },
  "total_telemetry_events": 27680,
  "max_stable_asset_count": 100
}
```
