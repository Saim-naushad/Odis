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

`demo_presentation` owns its cadence directly in `backend/simulator/scenario_script.py` (`cadence_for_script`) rather than through Compose environment defaults — the script picks a fast cadence whenever an operator hasn't explicitly overridden one of the three cadence env vars away from the platform default:

| Setting | Value |
|---------|-------|
| `SIMULATOR_SCENARIO_SCRIPT` | `demo_presentation` |
| `SIMULATOR_CORE_PUBLISH_INTERVAL_SECONDS` | 10 |
| `SIMULATOR_DERIVED_PUBLISH_INTERVAL_SECONDS` | 30 |
| `SIMULATOR_SIM_DT_SECONDS` | 90 |

This is a 9x sim:real ratio (vs. the platform default's 3x) — needed because health-status classification requires ≥8 core samples of a consistent trend (`trend_detector.py` / `time_series_analysis.py`), and a higher ratio compresses enough of the simulator's own load cycle into each phase to keep that classification from competing with the temperature fault signal (see the comment above `_PRESENTATION_CADENCE` for the full rationale, empirically validated against clean-database runs).

A ~6:40 presentation accumulates well under 250 core observations per asset (comfortably under the 500-history drain threshold), so the queue remains bounded — confirmed via `reasoning_jobs_pending` staying at 0 throughout validation runs.

### Realistic mode (disabled)

`demo_realistic` is implemented but **not enabled** in Compose, and is unaffected by the presentation cadence above — `cadence_for_script` returns `None` for it, so it runs at whatever `SIMULATOR_CORE_PUBLISH_INTERVAL_SECONDS` etc. the operator configures (see [Startup](#startup) for the override command). At 1,500+ observations per asset, presentation-speed ingest outpaces worker drain; a 2–4 hour run would grow the queue without bound.

**Future work (separate PR):** bounded reasoning windows or incremental reasoning — not in PR141.

### Queue-lag acceptance

| Mode | Max pending jobs | Max oldest-pending age |
|------|------------------|------------------------|
| Presentation (~6:40) | 25 | 120 s |
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
| `demo_presentation` | ~6:40 scripted walkthrough: baseline → cooling degradation → warning/critical → recovery (default) |
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

### Long-form realistic validation

`demo_realistic` is unaffected by `demo_presentation`'s fast cadence — it
runs at whatever cadence you set explicitly:

```bash
SIMULATOR_SCENARIO_SCRIPT=demo_realistic \
SIMULATOR_CORE_PUBLISH_INTERVAL_SECONDS=15 \
SIMULATOR_DERIVED_PUBLISH_INTERVAL_SECONDS=60 \
SIMULATOR_SIM_DT_SECONDS=45 \
  docker compose --profile demo up --build -d
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
5. Run `demo_presentation` to observe the full baseline → cooling degradation → warning/critical → recovery arc on stack-01 (~6:40)

---

## Reproducible screenshots & demo video

`demo_presentation` is deterministic and safe to re-record from: the
simulator advances plant physics with a first-order-lag model (no RNG), and
`PRESENTATION_PHASES` (`backend/simulator/scenario_script.py`) is a fixed,
ordered phase list. Re-running from a clean database reproduces the same
narrative beats in the same order every time — no new "demo mode" subsystem
is needed, only a repeatable procedure.

As of this PR, `demo_presentation` also owns a bespoke, fast cadence (see
[Throughput and cadence](#throughput-and-cadence)) so the whole walkthrough —
healthy baseline, cooling degradation, warning, critical, and a fully-settled
recovery — takes **~6:40** instead of the previous ~17:45, without touching
detectors, thresholds, health scoring, or the planner.

### Recording procedure

```bash
docker compose down -v   # clean state — required for a reproducible run
docker compose --profile demo up --build -d
docker compose logs -f demo-plant   # watch for phase-change lines as your recording cue
```

The simulator logs a line on every scripted phase transition:

```
[demo:demo_presentation] phase changed -> cooling_degradation (target=fuel-cell-stack-01)
```

Use these lines as the on-screen cue for when each *scenario* phase starts —
but note the health-status badge (NORMAL/WARNING/CRITICAL) lags a phase
boundary by tens of seconds (see the table below); don't assume the badge
flips the instant a phase-change line appears.

### Verified timing (presentation cadence)

**Superseded 2026-07-23**: the table this section used to carry (CRITICAL
holding ~30s, then WARNING holding until a settled NORMAL by ~06:12) was
measured against a real bug and is no longer accurate — see
[Known limitations](#known-limitations) for the root cause and fix
(`backend/app/application/reasoning_compatibility.py`'s legacy trend calls
silently used an 8-sample window instead of the platform's configured
20-sample `observation_window`, which is short enough to be less than one
Plant Alpha load-cycle at demo cadence). Before the fix, stack-01's health
status flapped between NORMAL/WARNING/CRITICAL roughly every 6–13 seconds,
continuously, for minutes at a time — the fix resolved that chaotic
multi-state flapping, but what replaced it is **not** a single held state
either, and this section now reports that honestly instead of repeating the
old claim.

`PRESENTATION_PHASES` durations are defined in *simulated* seconds; at the
presentation cadence (`SIMULATOR_CORE_PUBLISH_INTERVAL_SECONDS=10`,
`SIMULATOR_SIM_DT_SECONDS=90`, a 9x sim:real ratio) they map to real time.
Unlike phase-boundary timing, health-status transitions are **not** purely a
function of elapsed sim-time — they depend on the platform's
reasoning/trend-window and notification state (outside the simulator).

**Post-fix verified behavior** (three rehearsal runs, `docker compose down
-v` between each, post `reasoning_compatibility.py` fix):

| Event | Observed | Notes |
|---|---|---|
| `normal_operation` starts | 00:00 | All four assets NORMAL (score 90), no notification — reproduced exactly across all three runs |
| `cooling_degradation` phase change (log line) | between 00:29 and 01:27 across runs | Real run-to-run variance in absolute wall-clock time before the first phase change — see the variance note below. Use the `phase changed` log line as the cue, not a fixed clock |
| Health first leaves NORMAL/90 | shortly after the phase change in each run | Score drops to 80, still NORMAL — matches the original "ramping but not yet a threshold breach" description |
| **stack-01 health alternates NORMAL(80) ⟷ WARNING(45)** | continuously, roughly every **28–32 seconds**, for the remainder of the observed window (10+ minutes) | This is the new steady-state behavior — a **regular, predictable two-state oscillation**, not a held state. It correlates with Plant Alpha's own load-cycling period at this cadence, and is plausibly a genuine (if not very presentable) reflection of the physical signal rather than a detector defect. **CRITICAL was not observed at all** in the post-fix rehearsals |
| `recovery` phase change (log line) | between 02:02 and 03:33 after the cooling-degradation phase change, across runs | Also shows real run-to-run variance — see below |
| A held, single NORMAL state | not observed within a 10+ minute window post-fix | The NORMAL⟷WARNING alternation continued through the entire observed `recovery` phase in every run; do not plan a shot around a firmly "settled" legacy badge |

**Real variance, not just measurement noise:** phase-change timing and the
legacy health-status arc were measured across three separate clean runs in
this session (two before the fix, one after) and did **not** reproduce the
same absolute wall-clock timing each time — e.g. the cooling-degradation→
recovery phase gap measured 122s in one run and 213s in another, despite
both using the same fixed simulated-second durations and cadence. The most
likely explanation is variable container/scenario-loop startup lag under
concurrent host load (these rehearsals ran alongside a full test-suite
execution and image rebuilds), not a code defect — but it means **this
table's timestamps are directional, not a clock to record against**. Always
do a fresh, unencumbered dry run immediately before the real recording
session, and cue off the `phase changed` log lines and the dashboard's own
state (or the digital-twin API) rather than a stopwatch.

For a shorter cut, the AI-Assisted Fault Diagnosis card (see
[AI-fault-alert milestone](#ai-fault-alert-milestone-kafka-path-v11) below)
is now the more reliable "hero" moment to build a short recording around —
it confirms and corroborates faster and more consistently than the legacy
health badge, and doesn't depend on the behavior described in this section.

Reshoot `docs/assets/dashboard-*.png` from a clean run whenever the layout
changes materially; the phase-change log lines make repeat takes consistent
without re-deriving timing by hand.

### AI-fault-alert milestone (Kafka path, v1.1)

The health-status arc above (NORMAL → WARNING → CRITICAL → recovery) is the
platform's original MQTT-path reasoning. In parallel, the same telemetry
tick also reaches Kafka (`SIMULATOR_TRANSPORT=kafka+http`, the default for
`demo-plant`), where the v1.1 AI-fault-alert pipeline produces its own,
separate milestone that the health-status timing above does not describe:

1. **Warm-up** — the fault-inference worker's per-asset session requires an
   11-sample warm-up window before it emits its first prediction.
2. **Candidate alert** — each subsequent sample gets a model prediction; a
   deterministic temporal-hysteresis alert policy (entry/exit persistence,
   not a single-sample threshold) confirms a candidate alert once it holds
   long enough — see [Uncalibrated Temporal Alert Policy](../uncalibrated-temporal-alert-policy.md).
3. **Deterministic corroboration** — a separate reasoning-bridge worker
   corroborates the confirmed alert against the platform's own persisted
   observations before it becomes operator-facing — see [Reasoning Bridge](../reasoning-bridge.md).
4. **Investigation appears** — a confirmed, corroborated investigation
   (with `diagnosed_fault_class`, corroboration result, and investigation
   status) becomes visible via the AI Fault Investigation panel and API —
   see [Fault Investigation Dashboard](../fault-investigation-dashboard.md).

This is exactly what `./scripts/validate_demo_environment.sh --walkthrough`
gates on: it starts polling for a confirmed investigation at
`DEMO_FAULT_CHECK_START_SECONDS` (default 130s into the run) and fails the
whole walkthrough if none appears by `DEMO_WALKTHROUGH_DEADLINE_SECONDS`
(default 450s / 7:30), logging `event=ai_fault_investigation_confirmed`
the moment it does. As a reference point (not a demo-specific measurement),
isolated single-asset benchmark evidence at the same ~9x sim:real
acceleration ratio recorded a 37.2s fault-onset-to-recommendation wall time
for this path — see the [v1.1 Performance Report](../release/v1.1-performance-report.md).

**Live-verified range (2026-07-23, three rehearsal runs):** confirmed +
corroborated (`corroboration_result` populated, recommendation `produced`
or `withheld`) between **~0:57 and ~2:18** after a clean stack start — real
run-to-run variance, not a fixed number; consistent with the phase-timing
variance noted above. In every run this was still faster and more
consistent than the legacy health badge reaching a first WARNING/CRITICAL
transition, and it does not depend on `reasoning_compatibility.py`'s
trend-window computation at all (that fix only touches the MQTT-path health
badge, not this pipeline). Also observed live: the diagnosed class is not
stable for the life of a run — in two of three rehearsals it later flipped
from `cooling_degradation` to `hydrogen_supply_issue` (`alert_transition_type:
class_changed`), and deterministic corroboration correctly downgraded that
to `not_corroborated` / a withheld recommendation both times. A `cleared`
(empty) investigation state was not observed within any single rehearsal's
~9–10 minute window — don't plan a recording step around it appearing
reliably.

For a recording session, treat this as a second thing to watch for
alongside the health-status badge: the AI Fault Investigation panel
populating is its own milestone, on its own timeline, driven by the Kafka
path rather than the MQTT path described above, and is the more reliable of
the two to build a recording around.

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

Presentation walkthrough (up to ~7:30, reports timings and queue depth):

```bash
./scripts/validate_demo_environment.sh --walkthrough
```

The walkthrough's fault-check start, recovery marker, and overall deadline
are tuned to `demo_presentation`'s ~6:40 schedule and are overridable via
`DEMO_FAULT_CHECK_START_SECONDS`, `DEMO_RECOVERY_MARKER_SECONDS`, and
`DEMO_WALKTHROUGH_DEADLINE_SECONDS` if `PRESENTATION_PHASES` changes.

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

- **Recovery settling time is not just the physical ramp:** `demo_presentation`'s `recovery` phase runs ~250s (not the ~100s its physical ramp alone needs) because returning to a *held, stable* NORMAL reading depends on the platform's trend window and append-only notifications aging out the stale fault classification. **Update 2026-07-23:** post the `reasoning_compatibility.py` observation-window fix below, a held NORMAL was not observed at all within a 10+ minute rehearsal window — health now alternates NORMAL(80)/WARNING(45) roughly every 28-32s indefinitely rather than settling. `PRESENTATION_PHASES` is still sized around the *phase* durations described here; treat the settling claim itself as superseded by the timing note in [Verified timing](#verified-timing-presentation-cadence).
- **Fresh stack for acceptance:** Run acceptance validation on a clean database for deterministic results (`docker compose down -v` before `up` and `./scripts/validate_demo_environment.sh`). Reusing a long-lived volume can leave benchmark assets, large observation history, or elevated digital twin latency that does not reflect a first-run demo.
- **Digital twin latency grows with session length:** Long-running demo sessions (roughly 15–20 minutes or more) may increase digital twin response time because the current reasoning pipeline reloads growing per-asset observation history on each run.
- **Expected, not a correctness bug:** That latency behavior is a known scalability characteristic of the present pipeline, tracked for a future performance PR (e.g. bounded reasoning windows). It does not indicate incorrect ingestion, scenario logic, or dashboard behavior.
- **PR141 scope:** This PR validates demo infrastructure and end-to-end MQTT ingestion through reasoning and the operator dashboard. It does not claim long-duration scalability; `demo_realistic` remains disabled for that reason.
- **Resolved: healthy peers reading CRITICAL alongside the actual fault target.** A clean `demo_presentation` run previously showed `fuel-cell-stack-02/03/04` reaching `CRITICAL` at the same time as the actual fault target (`fuel-cell-stack-01`), and staying there through `recovery`, with no fault ever injected into their physics model. Root cause: `VariationDetector`'s threshold and `TrendDetector`'s first-vs-last comparison were both miscalibrated for Plant Alpha's real sinusoidal load-cycling amplitude, and reasoning reloaded unbounded observation history on every run so a resolved fault's stale extremes never aged out. Fixed via `ReasoningSessionConfig.observation_window` (bounded, per-measurement-type recent history), a recalibrated `HIGH_VARIATION_THRESHOLD`, and a `TrendDetector` rewrite (split-half mean comparison instead of endpoint comparison) — see `docs/architecture.md`'s reasoning-pipeline section.
- **Resolved: transient false WARNING/CRITICAL on healthy peers, cold-start and mid-session.** A later clean-stack characterization run found a smaller residual: individual healthy, unfaulted assets would briefly flip to `WARNING` or `CRITICAL` (a stale `OPEN` notification, since notifications are append-only and don't auto-clear when health recovers) throughout a session, not just at startup. Two distinct causes, both outside the core reasoning pipeline and the `DecisionPlanner`: (1) `TrendDetector`'s split-half comparison degenerates toward a raw endpoint comparison at very low sample counts (`n=2` gives one point per half) — verified against real telemetry, ratios spiked as high as 2.2x threshold at `n=2-7` before settling under 0.72 from `n=8` on. (2) A second, separate, previously-uncalibrated trend algorithm in the backend platform layer (`backend/app/application/time_series_analysis.py`, used only for `OperationalStateEngine`'s health-score penalty) was pinned at a fixed 5-sample window for the life of the session, not just at startup, and its volatility measure divided step noise by *net window drift* — which trends toward zero for any window that straddles a peak or trough of an oscillating signal, inflating `volatility_score` to 90-100 almost continuously even for a perfectly healthy asset. Fixed by requiring at least one full load-cycle's worth of history (8 samples, matching the cycle length in the cadence comment below) before either module trusts a directional classification, and widening the legacy module's window to match. Verified on a fresh clean stack: all four assets read `NORMAL` (health score 90) at baseline with no notification present, and the value held for the duration of a full `normal_operation` window.
- **Resolved: chaotic multi-state health flapping on the fault target itself.** A 2026-07-23 pre-recording audit found `fuel-cell-stack-01` (the actual fault target, not a healthy peer) cycling through NORMAL/WARNING/CRITICAL roughly every 6–13 seconds, continuously, for minutes at a time during `cooling_degradation`/`recovery` — distinct from the two healthy-peer issues above. Root cause: `backend/app/application/reasoning_compatibility.py`'s `build_explainable_decision` called `analyze_trend`/`analyze_trend_diagnostics` without an explicit `observation_window`, silently falling back to those functions' own 8-sample minimum instead of the platform's configured `DEFAULT_REASONING_SESSION_CONFIG.observation_window` (20) — a value already sized (see the cadence comment in `reasoning_config.py`) to span multiple Plant Alpha load-cycles specifically to prevent this failure mode, but never wired through to this call site. At presentation cadence, 8 samples is *less* than one full load-cycle, so the window's phase relative to the cycle flipped the classified trend direction on nearly every reasoning run. Fixed by passing the platform's configured window through explicitly (no threshold, detector, or `DecisionPlanner` changes); regression test: `tests/backend/test_reasoning_compatibility.py::test_build_explainable_decision_uses_platform_observation_window_not_legacy_minimum`. **This did not fully eliminate oscillation** — see the updated [Verified timing](#verified-timing-presentation-cadence) table for the new, much calmer but still-oscillating steady state.
- **Remaining limitation: one primary measurement per reasoning run.** The fix above does not make every fault type discriminable simultaneously — Plant Alpha's `cooling_degradation` and `hydrogen_supply_issue` faults are physically orthogonal (temperature vs. current/fuel_flow), and a single fixed primary-measurement preference cannot serve both without risking a regression in one to fix the other. See `docs/architecture.md`'s "Known limitation: single primary measurement per run"; multi-signal reasoning is planned as the first architectural milestone after v1.0, not forced into this release. Do a dry run of your recording window before shooting to confirm the specific scenario you intend to record behaves as expected.

---

## Related documentation

- [Simulator](../simulator.md)
- [Fuel cell operational profile](../profiles/fuel_cell_profile.md)
- [Docker Runtime](docker-runtime.md)
