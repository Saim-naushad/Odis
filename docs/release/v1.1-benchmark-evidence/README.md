# v1.1 benchmark evidence

Raw per-run artifacts backing [../v1.1-performance-report.md](../v1.1-performance-report.md)
— one repetition per configuration (see that report's Limitations section).
Each directory is produced by `scripts/benchmark_odis` and contains
`config.json`, `environment.json`, `raw-metrics.json`, `summary.json`, and
`report.md`. Directory names encode `<timestamp>-<scenario>-<assets>a-r<repetition>`.

- `*-normal-operation-{1,10,50,100}a-r0` — Scenario A (healthy throughput) scale matrix
- `*-cooling-degradation-{1,10,50,100}a-r0` — Scenario B (fault lifecycle) scale matrix
- `20260723054616-cooling-degradation-1a-r0` — `--mode reliability` run (replay idempotency, malformed telemetry, outbox/Kafka-outage recovery, AI-investigation/Redis-outage durability)

Regenerate with `python -m scripts.benchmark_odis` (see
[../../benchmarking.md](../../benchmarking.md)); new ad-hoc runs default to
`benchmark-results/` (gitignored) unless pointed at this directory
explicitly with `--output-dir`.
