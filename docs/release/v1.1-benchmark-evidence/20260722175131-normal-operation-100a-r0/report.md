# Benchmark run 20260722175131-normal-operation-100a-r0

Mode: `performance` · Scenario: `normal_operation` · Assets: 100 · Duration: 150.0s

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
- **benchmark_timestamp**: 2026-07-22T17:51:32.065452+00:00

## Summary

```json
{
  "hop_latencies": {
    "telemetry_acquisition_to_inference_publish_ms": {
      "metric_name": "telemetry_acquisition_to_inference_publish_ms",
      "count": 1615,
      "excluded_count": 0,
      "median_ms": 5148.438999999999,
      "p95_ms": 9964.559,
      "max_ms": 11917.778999999999
    },
    "alert_publish_to_reasoning_persist_ms": {
      "metric_name": "alert_publish_to_reasoning_persist_ms",
      "count": 0,
      "excluded_count": 0,
      "median_ms": 0.0,
      "p95_ms": 0.0,
      "max_ms": 0.0
    },
    "source_sample_to_durable_reasoning_record_ms": {
      "metric_name": "source_sample_to_durable_reasoning_record_ms",
      "count": 0,
      "excluded_count": 0,
      "median_ms": 0.0,
      "p95_ms": 0.0,
      "max_ms": 0.0
    },
    "reasoning_persist_to_api_observed_ms": {
      "metric_name": "reasoning_persist_to_api_observed_ms",
      "count": 0,
      "excluded_count": 0,
      "median_ms": 0.0,
      "p95_ms": 0.0,
      "max_ms": 0.0
    },
    "reasoning_persist_to_sse_observed_ms": {
      "metric_name": "reasoning_persist_to_sse_observed_ms",
      "count": 0,
      "excluded_count": 0,
      "median_ms": 0.0,
      "p95_ms": 0.0,
      "max_ms": 0.0
    },
    "fault_onset_to_confirmation_sim_seconds": null,
    "fault_onset_to_recommendation_wall_ms": null
  },
  "onset": {
    "fault_onset_sample_index": 2,
    "fault_onset_source_timestamp": null,
    "target_asset": "fuel-cell-stack-01"
  },
  "throughput_including_warmup": {
    "telemetry_measurement_events_per_second": 86.18,
    "complete_samples_per_second": 10.766666666666667,
    "valid_inference_results_per_second": 3.433333333333333,
    "all_inference_results_per_second": 10.766666666666667,
    "measurement_window_seconds": 150.0,
    "steady_state": false
  },
  "steady_state_boundary": "2026-07-22 17:53:47.783239+00:00",
  "reconciliation": {
    "observation_rows": 12920,
    "timeline_event_rows": 20904,
    "ai_fault_evidence_rows": 0,
    "outbox_pending_rows": 3,
    "distinct_investigation_ids": 0
  },
  "consumer_lag_at_end": {
    "odis.telemetry.observations.v1": 0,
    "odis.fault.alert-transitions.v1": 0
  },
  "resource_usage": {
    "odis-benchmark-20260722175131-normal-operation-100a-r0-api-1": {
      "container": "odis-benchmark-20260722175131-normal-operation-100a-r0-api-1",
      "sample_count": 20,
      "avg_cpu_percent": 62.359,
      "peak_cpu_percent": 95.65,
      "avg_memory_bytes": 111717384.192,
      "peak_memory_bytes": 120481382.4
    },
    "odis-benchmark-20260722175131-normal-operation-100a-r0-worker-1": {
      "container": "odis-benchmark-20260722175131-normal-operation-100a-r0-worker-1",
      "sample_count": 20,
      "avg_cpu_percent": 74.161,
      "peak_cpu_percent": 84.49,
      "avg_memory_bytes": 86543171.584,
      "peak_memory_bytes": 100631838.72
    },
    "odis-benchmark-20260722175131-normal-operation-100a-r0-reasoning-bridge-worker-1": {
      "container": "odis-benchmark-20260722175131-normal-operation-100a-r0-reasoning-bridge-worker-1",
      "sample_count": 20,
      "avg_cpu_percent": 0.832,
      "peak_cpu_percent": 2.79,
      "avg_memory_bytes": 74665951.23200001,
      "peak_memory_bytes": 74690068.48
    },
    "odis-benchmark-20260722175131-normal-operation-100a-r0-fault-inference-worker-1": {
      "container": "odis-benchmark-20260722175131-normal-operation-100a-r0-fault-inference-worker-1",
      "sample_count": 19,
      "avg_cpu_percent": 11.915263157894737,
      "peak_cpu_percent": 25.95,
      "avg_memory_bytes": 114995674.2736842,
      "peak_memory_bytes": 115448217.6
    }
  },
  "observability": {
    "api_poll_interval_seconds": 2.0,
    "sse_connection_established_at": "2026-07-22 22:51:53.400129+05:00",
    "sse_subscribed_before_simulator_launch": true,
    "malformed_kafka_messages_observed": 0
  },
  "total_telemetry_events": 12927,
  "max_stable_asset_count": 100
}
```
