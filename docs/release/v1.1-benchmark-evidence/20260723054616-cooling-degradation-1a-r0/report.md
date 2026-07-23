# Benchmark run 20260723054616-cooling-degradation-1a-r0

Mode: `reliability` · Scenario: `cooling_degradation` · Assets: 1 · Duration: 220.0s

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
- **benchmark_timestamp**: 2026-07-23T05:46:16.873980+00:00

## Summary

```json
{
  "replay_idempotency": {
    "replayed_event_count": 1,
    "ai_fault_evidence_row_count_before": 1,
    "ai_fault_evidence_row_count_after": 1,
    "passed": true
  },
  "malformed_telemetry_counter_total": 3.0,
  "fault_inference_worker_still_running": true,
  "outbox_kafka_leg_recovery": {
    "dispatched_at_stayed_null_during_outage": true,
    "dispatched_exactly_once_after_recovery": true,
    "passed": true
  },
  "ai_investigation_durability": {
    "outbox_row_dispatched_despite_redis_outage": true,
    "note": "dispatch() completed normally with Redis stopped"
  }
}
```
