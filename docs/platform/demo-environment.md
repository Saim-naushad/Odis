# Demo Environment

This document describes the Plant Alpha demonstration environment for ODIS. It exercises the full platform path — simulator → MQTT → bridge → API → TimescaleDB → worker → digital twin → dashboard — without demo-only production code.

For simulator internals, see [Simulator](../simulator.md). For platform context, see [Platform Architecture](platform-architecture.md).

---

## Architecture

```mermaid
flowchart TB
    demoPlant["demo-plant"]
    mosquitto["mosquitto"]
    bridge["mqtt-bridge"]
    api["api"]
    worker["worker"]
    postgres[("TimescaleDB")]
    frontend["frontend"]

    demoPlant --> mosquitto
    mosquitto --> bridge
    bridge --> api
    api --> postgres
    api --> worker
    worker --> postgres
    frontend --> api
```

MQTT topic convention:

```
odis/v1/plant-alpha/{asset_id}/telemetry/{measurement_type}
```

---

## Plant Alpha

| Asset | Role |
|-------|------|
| `fuel-cell-stack-01` | Primary fault target |
| `fuel-cell-stack-02` | Healthy peer |
| `fuel-cell-stack-03` | Healthy peer |
| `fuel-cell-stack-04` | Healthy peer |

### Measurements

**Core (reasoning profile, every 15s):** `stack_temperature`, `stack_pressure`, `current`, `voltage`, `fuel_flow`

**Derived (display, every 60s):** `power_output`, `efficiency`, `coolant_flow`

`stack_pressure` is the hydrogen/manifold pressure proxy.

### Asset identity limitation

The dashboard discovers assets from observations only. `DigitalTwinService` synthesizes `asset_name` from the asset id, with `asset_type: "unknown"` and `location: "unknown"`. PR141 does not add an asset registry or demo-only frontend metadata.

---

## Throughput and cadence

Every observation enqueues one reasoning job. Job duration grows with per-asset observation history because each run reloads all observations.

### Postgres benchmark results (July 2026)

Run with:

```bash
docker compose up -d postgres api worker
PYTHONPATH=src:. python scripts/benchmark_reasoning_worker.py \
  --database-url postgresql+psycopg://odis:odis@localhost:5432/odis
```

| History / asset | Avg job | P95 job | Throughput | `list_by_asset` | Presentation queue Δ/min | Realistic queue Δ/min |
|-----------------|---------|---------|------------|-----------------|---------------------------|------------------------|
| 100 | 0.225 s | 0.325 s | 4.45 jobs/s | 1.6 ms | −175 | −221 |
| 500 | 0.355 s | 0.492 s | 2.81 jobs/s | 5.2 ms | −77 | −123 |
| 1,500 | 0.817 s | 1.486 s | 1.22 jobs/s | 14.5 ms | **+19** | −33 |
| 3,000 | 1.362 s | 1.556 s | 0.73 jobs/s | 28.7 ms | **+48** | **+2** |

Presentation ingest: **1.53 jobs/s** (4 assets × 5 core / 15 s + 4 × 3 derived / 60 s).  
Realistic ingest: **0.77 jobs/s** (4 assets × 5 core / 30 s + 4 × 3 derived / 120 s).

### Default cadence (presentation — enabled)

| Setting | Value |
|---------|-------|
| `SIMULATOR_SCENARIO_SCRIPT` | `demo_presentation` |
| `SIMULATOR_CORE_PUBLISH_INTERVAL_SECONDS` | 15 |
| `SIMULATOR_DERIVED_PUBLISH_INTERVAL_SECONDS` | 60 |
| `SIMULATOR_SIM_DT_SECONDS` | 45 |

A 12–15 minute presentation accumulates ~240–300 core observations per asset (under the 500-history drain threshold), so the queue remains bounded.

### Realistic mode (disabled)

`demo_realistic` is implemented but **not enabled** in Compose. At 1,500+ observations per asset, presentation ingest outpaces worker drain; a 2–4 hour run would grow the queue without bound.

**Future work (separate PR):** bounded reasoning windows or incremental reasoning — not in PR141.

### Queue-lag acceptance

| Mode | Max pending jobs | Max oldest-pending age |
|------|------------------|------------------------|
| Presentation (~15 min) | 25 | 120 s |
| Realistic (2–4 h) | 50 | 300 s |

`demo_realistic` is enabled only when the Postgres benchmark shows non-positive queue growth at realistic ingest for histories up to 3,000 observations per asset. See benchmark results in this repository's validation output.

---

## Scenarios

| Scenario | Effect |
|----------|--------|
| `normal_operation` | Healthy sinusoidal load cycling |
| `cooling_degradation` | Cooling efficiency ramp-down on stack-01 |
| `hydrogen_supply_issue` | Fuel supply factor ramp-down on stack-01 |
| `sensor_anomaly` | Temperature sensor bias only |
| `recovery` | Restore cooling, fuel, and sensor bias |
| `demo_presentation` | ~12 min scripted walkthrough (default) |
| `demo_realistic` | Long-running script (implemented, **not enabled** — see throughput limits) |

Trend and health changes require **multiple core publish cycles** on `stack_temperature` — not a single multi-metric burst.

---

## Startup

### Full Compose demo (MQTT required)

```bash
docker compose --profile demo up --build -d
./scripts/validate_demo_environment.sh
open http://localhost:8080
```

### Local HTTP fallback (development only — not E2E acceptance)

```bash
SIMULATOR_TRANSPORT=http python -m backend.simulator --scenario normal_operation
```

---

## Dashboard walkthrough

1. Open `http://localhost:8080`
2. Use **Last hour** and **Raw** telemetry until ≥1 hour of data exists
3. Fleet strip populates as observations arrive (~15s per asset)
4. Health scores appear after ≥2 `stack_temperature` samples (~30s)
5. Run `demo_presentation` to observe cooling → recovery → hydrogen supply phases on stack-01

---

## Reproducible screenshots & demo video

`demo_presentation` is already deterministic and safe to re-record from: the
simulator advances plant physics with a first-order-lag model (no RNG), and
`PRESENTATION_PHASES` (`backend/simulator/scenario_script.py`) is a fixed,
ordered phase list. Re-running from a clean database reproduces the same
narrative beats in the same order every time — no new "demo mode" subsystem
is needed, only a repeatable procedure.

### Recording procedure

```bash
docker compose down -v   # clean state — required for a reproducible run
docker compose --profile demo up --build -d
docker compose logs -f demo-plant   # watch for phase-change lines as your recording cue
```

The simulator now logs a line on every scripted phase transition:

```
[demo:demo_presentation] phase changed -> cooling_degradation (target=fuel-cell-stack-01)
```

Use these lines as the on-screen cue for when to capture each beat, instead
of estimating from wall-clock time.

### Approximate timing (default cadence)

Phase durations are defined in *simulated* seconds; at the default cadence
(`SIMULATOR_CORE_PUBLISH_INTERVAL_SECONDS=15`, `SIMULATOR_SIM_DT_SECONDS=45`)
each tick advances sim-time 3x faster than real time
(`sim_dt_seconds / core_interval`). That gives this real-world timeline for
the full `demo_presentation` script. It is also the recommended recording and
narration order — each phase builds on the last (baseline, fault, response,
recovery, second fault type), so cutting or reordering loses that narrative:

| Real time (mm:ss) | Phase | What to capture | Talking point |
|---|---|---|---|
| 00:00 | `normal_operation` starts | Fleet strip, all four assets healthy — good for an optional "baseline" shot | All four Plant Alpha stacks healthy; telemetry is live over MQTT, not mocked |
| 02:00 | `cooling_degradation` starts on stack-01 | Health score beginning to drop | A fault is injected in the simulator's physics model — not a scripted UI state |
| ~04:00–08:00 | mid cooling degradation | Recommendation/notification appear once thresholds are crossed — this is the primary hero shot (fleet overview + investigation timeline) | The recommendation and priority come from the deterministic reasoning pipeline (evidence → signal → assessment → decision), traceable in the investigation timeline — not a black-box ML call |
| 08:00 | `recovery` starts | Health trending back up | Reasoning re-assesses on new evidence automatically; no manual reset |
| 12:00 | `hydrogen_supply_issue` starts on stack-01 | Second fault type, alternate recommendation category | Same detectors and planner produce a different, correctly-categorized recommendation for an unrelated fault mode |
| 16:00 | `recovery` starts | Final recovery | Second recovery closes the loop — good moment to show the investigation lifecycle (acknowledge → investigating → resolved) if not shown earlier |
| 18:00 | script ends, loops on `normal_operation` | — | — |

Total script length: **~18 minutes** real time. If any of the cadence env
vars above are overridden, recompute using the same ratio — don't hand-tune
against a specific run's wall-clock timing, since it drifts with config.

For a video under ~5 minutes, the ~04:00–08:00 cooling-degradation window plus
one investigation-lifecycle transition is the minimum viable cut: it shows
live ingestion, a real fault, an explainable recommendation, and an operator
response in one continuous segment.

Reshoot `docs/assets/dashboard-*.png` from a clean run whenever the layout
changes materially; the phase-change log lines make repeat takes consistent
without re-deriving timing by hand.

---

## Validation

Demo acceptance requires a **clean database**. Reset volumes before validation:

```bash
docker compose down -v
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile demo up --build -d
```

### Acceptance script

```bash
./scripts/validate_demo_environment.sh
```

Required checks (fail on error):

- exactly four Plant Alpha assets (`fuel-cell-stack-01` … `04`), no benchmark assets
- observations stored and at least one reasoning job completed
- reasoning queue at or below the configured threshold
- digital twin for `fuel-cell-stack-01` returns HTTP 200 within the timeout (not a passing run if it times out)

Recorded on success: response status, latency, health status/score, recommendation category/priority, notification presence, timeline preview length.

Presentation walkthrough (12–15 minutes, reports timings and queue depth):

```bash
./scripts/validate_demo_environment.sh --walkthrough
```

### Characterized scenario outcomes (deterministic)

Through the real reasoning pipeline:

- **Cooling degradation:** cooling efficiency falls below 0.75; operational state shows a meaningful transition (health, risk, or primary driver); recommendation and notification appear when policy thresholds warrant; timeline gains trend/notification/health events; recovery restores cooling efficiency ≥ 0.8.
- **Hydrogen supply:** fuel delivery and current fall; reasoning outcome changes (driver, health/risk, or recommendation).
- **Sensor anomaly:** temperature bias is injected; reasoning outcome changes (assessment, confidence, alternative hypotheses, or primary driver).

### Test suite

```bash
pytest tests/backend/simulator tests/integration/test_demo_scenario_reasoning.py
ODIS_DEMO_SMOKE=1 pytest tests/integration/test_demo_mqtt_smoke.py
./scripts/validate_demo_environment.sh
```

---

## Known limitations

- **Fresh stack for acceptance:** Run acceptance validation on a clean database for deterministic results (`docker compose down -v` before `up` and `./scripts/validate_demo_environment.sh`). Reusing a long-lived volume can leave benchmark assets, large observation history, or elevated digital twin latency that does not reflect a first-run demo.
- **Digital twin latency grows with session length:** Long-running demo sessions (roughly 15–20 minutes or more) may increase digital twin response time because the current reasoning pipeline reloads growing per-asset observation history on each run.
- **Expected, not a correctness bug:** That latency behavior is a known scalability characteristic of the present pipeline, tracked for a future performance PR (e.g. bounded reasoning windows). It does not indicate incorrect ingestion, scenario logic, or dashboard behavior.
- **PR141 scope:** This PR validates demo infrastructure and end-to-end MQTT ingestion through reasoning and the operator dashboard. It does not claim long-duration scalability; `demo_realistic` remains disabled for that reason.
- **Resolved: healthy peers reading CRITICAL alongside the actual fault target.** A clean `demo_presentation` run previously showed `fuel-cell-stack-02/03/04` reaching `CRITICAL` at the same time as the actual fault target (`fuel-cell-stack-01`), and staying there through `recovery`, with no fault ever injected into their physics model. Root cause: `VariationDetector`'s threshold and `TrendDetector`'s first-vs-last comparison were both miscalibrated for Plant Alpha's real sinusoidal load-cycling amplitude, and reasoning reloaded unbounded observation history on every run so a resolved fault's stale extremes never aged out. Fixed via `ReasoningSessionConfig.observation_window` (bounded, per-measurement-type recent history), a recalibrated `HIGH_VARIATION_THRESHOLD`, and a `TrendDetector` rewrite (split-half mean comparison instead of endpoint comparison) — see `docs/architecture.md`'s reasoning-pipeline section. Verified on a fresh clean stack: all four assets read `NORMAL` at baseline.
- **Remaining limitation: one primary measurement per reasoning run.** The fix above does not make every fault type discriminable simultaneously — Plant Alpha's `cooling_degradation` and `hydrogen_supply_issue` faults are physically orthogonal (temperature vs. current/fuel_flow), and a single fixed primary-measurement preference cannot serve both without risking a regression in one to fix the other. See `docs/architecture.md`'s "Known limitation: single primary measurement per run"; multi-signal reasoning is planned as the first architectural milestone after v1.0, not forced into this release. Do a dry run of your recording window before shooting to confirm the specific scenario you intend to record behaves as expected.

---

## Related documentation

- [Simulator](../simulator.md)
- [Fuel cell operational profile](../profiles/fuel_cell_profile.md)
- [Docker Runtime](docker-runtime.md)
