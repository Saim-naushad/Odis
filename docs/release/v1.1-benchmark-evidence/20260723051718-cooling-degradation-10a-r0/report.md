# Benchmark run 20260723051718-cooling-degradation-10a-r0

Mode: `performance` · Scenario: `cooling_degradation` · Assets: 10 · Duration: 260.0s

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
- **benchmark_timestamp**: 2026-07-23T05:17:18.709851+00:00

## Summary

```json
{
  "hop_latencies": {
    "telemetry_acquisition_to_inference_publish_ms": {
      "metric_name": "telemetry_acquisition_to_inference_publish_ms",
      "count": 1958,
      "excluded_count": 0,
      "median_ms": 550.809,
      "p95_ms": 1616.895,
      "max_ms": 3212.445
    },
    "alert_publish_to_reasoning_persist_ms": {
      "metric_name": "alert_publish_to_reasoning_persist_ms",
      "count": 1,
      "excluded_count": 0,
      "median_ms": 71.71600000000001,
      "p95_ms": 71.71600000000001,
      "max_ms": 71.71600000000001
    },
    "source_sample_to_durable_reasoning_record_ms": {
      "metric_name": "source_sample_to_durable_reasoning_record_ms",
      "count": 1,
      "excluded_count": 0,
      "median_ms": 83.76899999999999,
      "p95_ms": 83.76899999999999,
      "max_ms": 83.76899999999999
    },
    "reasoning_persist_to_api_observed_ms": {
      "metric_name": "reasoning_persist_to_api_observed_ms",
      "count": 1,
      "excluded_count": 0,
      "median_ms": 1674.5,
      "p95_ms": 1674.5,
      "max_ms": 1674.5
    },
    "reasoning_persist_to_sse_observed_ms": {
      "metric_name": "reasoning_persist_to_sse_observed_ms",
      "count": 1,
      "excluded_count": 0,
      "median_ms": 32.925999999999995,
      "p95_ms": 32.925999999999995,
      "max_ms": 32.925999999999995
    },
    "fault_onset_to_confirmation_sim_seconds": 330.0,
    "fault_onset_to_recommendation_wall_ms": {
      "milliseconds": 41424.655,
      "valid": true
    }
  },
  "onset": {
    "fault_onset_sample_index": 2,
    "fault_onset_source_timestamp": "2026-07-23 05:17:55.548253+00:00",
    "target_asset": "fuel-cell-stack-01"
  },
  "throughput_including_warmup": {
    "telemetry_measurement_events_per_second": 60.246153846153845,
    "complete_samples_per_second": 7.530769230769231,
    "valid_inference_results_per_second": 7.107692307692307,
    "all_inference_results_per_second": 7.530769230769231,
    "measurement_window_seconds": 260.0,
    "steady_state": false
  },
  "steady_state_boundary": "2026-07-23 05:18:07.986275+00:00",
  "reconciliation": {
    "observation_rows": 15657,
    "timeline_event_rows": 23366,
    "ai_fault_evidence_rows": 1,
    "outbox_pending_rows": 0,
    "distinct_investigation_ids": 1
  },
  "consumer_lag_at_end": {
    "odis.telemetry.observations.v1": 0,
    "odis.fault.alert-transitions.v1": 0
  },
  "resource_usage": {
    "odis-benchmark-20260723051718-cooling-degradation-10a-r0-api-1": {
      "container": "odis-benchmark-20260723051718-cooling-degradation-10a-r0-api-1",
      "sample_count": 32,
      "avg_cpu_percent": 43.96,
      "peak_cpu_percent": 143.21,
      "avg_memory_bytes": 112023961.6,
      "peak_memory_bytes": 112931635.2
    },
    "odis-benchmark-20260723051718-cooling-degradation-10a-r0-worker-1": {
      "container": "odis-benchmark-20260723051718-cooling-degradation-10a-r0-worker-1",
      "sample_count": 32,
      "avg_cpu_percent": 78.6434375,
      "peak_cpu_percent": 89.9,
      "avg_memory_bytes": 102952468.48,
      "peak_memory_bytes": 123207680.0
    },
    "odis-benchmark-20260723051718-cooling-degradation-10a-r0-reasoning-bridge-worker-1": {
      "container": "odis-benchmark-20260723051718-cooling-degradation-10a-r0-reasoning-bridge-worker-1",
      "sample_count": 32,
      "avg_cpu_percent": 0.7853125,
      "peak_cpu_percent": 4.03,
      "avg_memory_bytes": 76487720.96000001,
      "peak_memory_bytes": 77080821.76
    },
    "odis-benchmark-20260723051718-cooling-degradation-10a-r0-fault-inference-worker-1": {
      "container": "odis-benchmark-20260723051718-cooling-degradation-10a-r0-fault-inference-worker-1",
      "sample_count": 32,
      "avg_cpu_percent": 9.688125,
      "peak_cpu_percent": 30.79,
      "avg_memory_bytes": 114622464.0,
      "peak_memory_bytes": 114923929.6
    }
  },
  "observability": {
    "api_poll_interval_seconds": 2.0,
    "sse_connection_established_at": "2026-07-23 10:17:52.563996+05:00",
    "sse_subscribed_before_simulator_launch": true,
    "malformed_kafka_messages_observed": 0
  },
  "total_telemetry_events": 15664,
  "max_stable_asset_count": 10
}
```
