# Benchmark run 20260722175453-cooling-degradation-1a-r0

Mode: `performance` · Scenario: `cooling_degradation` · Assets: 1 · Duration: 220.0s

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
- **benchmark_timestamp**: 2026-07-22T17:54:53.397732+00:00

## Summary

```json
{
  "hop_latencies": {
    "telemetry_acquisition_to_inference_publish_ms": {
      "metric_name": "telemetry_acquisition_to_inference_publish_ms",
      "count": 113,
      "excluded_count": 0,
      "median_ms": 31.669999999999998,
      "p95_ms": 74.86800000000001,
      "max_ms": 395.34200000000004
    },
    "alert_publish_to_reasoning_persist_ms": {
      "metric_name": "alert_publish_to_reasoning_persist_ms",
      "count": 1,
      "excluded_count": 0,
      "median_ms": 68.523,
      "p95_ms": 68.523,
      "max_ms": 68.523
    },
    "source_sample_to_durable_reasoning_record_ms": {
      "metric_name": "source_sample_to_durable_reasoning_record_ms",
      "count": 1,
      "excluded_count": 0,
      "median_ms": 91.52000000000001,
      "p95_ms": 91.52000000000001,
      "max_ms": 91.52000000000001
    },
    "reasoning_persist_to_api_observed_ms": {
      "metric_name": "reasoning_persist_to_api_observed_ms",
      "count": 1,
      "excluded_count": 0,
      "median_ms": 663.1270000000001,
      "p95_ms": 663.1270000000001,
      "max_ms": 663.1270000000001
    },
    "reasoning_persist_to_sse_observed_ms": {
      "metric_name": "reasoning_persist_to_sse_observed_ms",
      "count": 1,
      "excluded_count": 0,
      "median_ms": 15.299999999999999,
      "p95_ms": 15.299999999999999,
      "max_ms": 15.299999999999999
    },
    "fault_onset_to_confirmation_sim_seconds": 330.0,
    "fault_onset_to_recommendation_wall_ms": {
      "milliseconds": 37212.326,
      "valid": true
    }
  },
  "onset": {
    "fault_onset_sample_index": 2,
    "fault_onset_source_timestamp": "2026-07-22 17:55:17.335138+00:00",
    "target_asset": "fuel-cell-stack-01"
  },
  "throughput_including_warmup": {
    "telemetry_measurement_events_per_second": 4.109090909090909,
    "complete_samples_per_second": 0.5136363636363637,
    "valid_inference_results_per_second": 0.4636363636363636,
    "all_inference_results_per_second": 0.5136363636363637,
    "measurement_window_seconds": 220.0,
    "steady_state": false
  },
  "steady_state_boundary": "2026-07-22 17:55:28.364336+00:00",
  "reconciliation": {
    "observation_rows": 899,
    "timeline_event_rows": 3963,
    "ai_fault_evidence_rows": 1,
    "outbox_pending_rows": 0,
    "distinct_investigation_ids": 1
  },
  "consumer_lag_at_end": {
    "odis.telemetry.observations.v1": 0,
    "odis.fault.alert-transitions.v1": 0
  },
  "resource_usage": {
    "odis-benchmark-20260722175453-cooling-degradation-1a-r0-api-1": {
      "container": "odis-benchmark-20260722175453-cooling-degradation-1a-r0-api-1",
      "sample_count": 27,
      "avg_cpu_percent": 7.981481481481482,
      "peak_cpu_percent": 26.79,
      "avg_memory_bytes": 111100122.45333333,
      "peak_memory_bytes": 111987916.8
    },
    "odis-benchmark-20260722175453-cooling-degradation-1a-r0-worker-1": {
      "container": "odis-benchmark-20260722175453-cooling-degradation-1a-r0-worker-1",
      "sample_count": 27,
      "avg_cpu_percent": 63.69518518518518,
      "peak_cpu_percent": 85.56,
      "avg_memory_bytes": 89187602.5837037,
      "peak_memory_bytes": 101093212.16
    },
    "odis-benchmark-20260722175453-cooling-degradation-1a-r0-reasoning-bridge-worker-1": {
      "container": "odis-benchmark-20260722175453-cooling-degradation-1a-r0-reasoning-bridge-worker-1",
      "sample_count": 27,
      "avg_cpu_percent": 1.7625925925925925,
      "peak_cpu_percent": 22.58,
      "avg_memory_bytes": 76466822.25777778,
      "peak_memory_bytes": 76808192.0
    },
    "odis-benchmark-20260722175453-cooling-degradation-1a-r0-fault-inference-worker-1": {
      "container": "odis-benchmark-20260722175453-cooling-degradation-1a-r0-fault-inference-worker-1",
      "sample_count": 27,
      "avg_cpu_percent": 2.684074074074074,
      "peak_cpu_percent": 32.72,
      "avg_memory_bytes": 114516150.04444444,
      "peak_memory_bytes": 114819072.0
    }
  },
  "observability": {
    "api_poll_interval_seconds": 2.0,
    "sse_connection_established_at": "2026-07-22 22:55:15.587632+05:00",
    "sse_subscribed_before_simulator_launch": true,
    "malformed_kafka_messages_observed": 0
  },
  "total_telemetry_events": 904,
  "max_stable_asset_count": 1
}
```
