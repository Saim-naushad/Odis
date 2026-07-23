# Benchmark run 20260722174841-normal-operation-50a-r0

Mode: `performance` · Scenario: `normal_operation` · Assets: 50 · Duration: 120.0s

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
- **benchmark_timestamp**: 2026-07-22T17:48:41.759453+00:00

## Summary

```json
{
  "hop_latencies": {
    "telemetry_acquisition_to_inference_publish_ms": {
      "metric_name": "telemetry_acquisition_to_inference_publish_ms",
      "count": 1273,
      "excluded_count": 0,
      "median_ms": 2547.151,
      "p95_ms": 5120.958,
      "max_ms": 8019.899
    },
    "alert_publish_to_reasoning_persist_ms": {
      "metric_name": "alert_publish_to_reasoning_persist_ms",
      "count": 4,
      "excluded_count": 0,
      "median_ms": 23.907,
      "p95_ms": 90.63,
      "max_ms": 90.63
    },
    "source_sample_to_durable_reasoning_record_ms": {
      "metric_name": "source_sample_to_durable_reasoning_record_ms",
      "count": 4,
      "excluded_count": 0,
      "median_ms": 2159.852,
      "p95_ms": 2370.815,
      "max_ms": 2370.815
    },
    "reasoning_persist_to_api_observed_ms": {
      "metric_name": "reasoning_persist_to_api_observed_ms",
      "count": 2,
      "excluded_count": 0,
      "median_ms": 49.706,
      "p95_ms": 239.518,
      "max_ms": 239.518
    },
    "reasoning_persist_to_sse_observed_ms": {
      "metric_name": "reasoning_persist_to_sse_observed_ms",
      "count": 4,
      "excluded_count": 0,
      "median_ms": 18.253999999999998,
      "p95_ms": 20.084,
      "max_ms": 20.084
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
    "telemetry_measurement_events_per_second": 84.86666666666666,
    "complete_samples_per_second": 10.608333333333333,
    "valid_inference_results_per_second": 6.025,
    "all_inference_results_per_second": 10.608333333333333,
    "measurement_window_seconds": 120.0,
    "steady_state": false
  },
  "steady_state_boundary": "2026-07-22 17:50:01.873363+00:00",
  "reconciliation": {
    "observation_rows": 10181,
    "timeline_event_rows": 16821,
    "ai_fault_evidence_rows": 4,
    "outbox_pending_rows": 0,
    "distinct_investigation_ids": 4
  },
  "consumer_lag_at_end": {
    "odis.telemetry.observations.v1": 0,
    "odis.fault.alert-transitions.v1": 0
  },
  "resource_usage": {
    "odis-benchmark-20260722174841-normal-operation-50a-r0-api-1": {
      "container": "odis-benchmark-20260722174841-normal-operation-50a-r0-api-1",
      "sample_count": 16,
      "avg_cpu_percent": 59.63875,
      "peak_cpu_percent": 77.42,
      "avg_memory_bytes": 111476736.0,
      "peak_memory_bytes": 112617062.4
    },
    "odis-benchmark-20260722174841-normal-operation-50a-r0-worker-1": {
      "container": "odis-benchmark-20260722174841-normal-operation-50a-r0-worker-1",
      "sample_count": 16,
      "avg_cpu_percent": 75.7225,
      "peak_cpu_percent": 85.7,
      "avg_memory_bytes": 86675292.16,
      "peak_memory_bytes": 100946411.52
    },
    "odis-benchmark-20260722174841-normal-operation-50a-r0-reasoning-bridge-worker-1": {
      "container": "odis-benchmark-20260722174841-normal-operation-50a-r0-reasoning-bridge-worker-1",
      "sample_count": 16,
      "avg_cpu_percent": 1.07,
      "peak_cpu_percent": 4.55,
      "avg_memory_bytes": 75084595.2,
      "peak_memory_bytes": 77080821.76
    },
    "odis-benchmark-20260722174841-normal-operation-50a-r0-fault-inference-worker-1": {
      "container": "odis-benchmark-20260722174841-normal-operation-50a-r0-fault-inference-worker-1",
      "sample_count": 16,
      "avg_cpu_percent": 10.55125,
      "peak_cpu_percent": 16.53,
      "avg_memory_bytes": 114740428.8,
      "peak_memory_bytes": 115028787.2
    }
  },
  "observability": {
    "api_poll_interval_seconds": 2.0,
    "sse_connection_established_at": "2026-07-22 22:49:02.698335+05:00",
    "sse_subscribed_before_simulator_launch": true,
    "malformed_kafka_messages_observed": 0
  },
  "total_telemetry_events": 10184,
  "max_stable_asset_count": 50
}
```
