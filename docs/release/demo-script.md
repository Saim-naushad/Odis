# v1.0.0 Demo Script (3–5 minutes)

Companion to [Screenshot Checklist](screenshot-checklist.md). Both draw from
the same `demo_presentation` recording session — see
[Demo Environment → Recording procedure](../platform/demo-environment.md#reproducible-screenshots--demo-video)
for exact startup and timing mechanics.

**Before recording:** start from a clean database
(`docker compose down -v && docker compose --profile demo up --build -d`)
and let `normal_operation` run for at least a minute before hitting record —
see the **Known risk** note at the end of this document. Watch
`docker compose logs -f demo-plant` for phase-change lines and use them as
cues instead of a stopwatch.

Target run time: **4 minutes**. Cut points are marked if you need to trim to 3.

---

## 1. Opening (0:00–0:20)

**On screen:** terminal, then switch to the dashboard at `http://localhost:8080`.

> "This is ODIS — an operational reasoning platform. It turns raw telemetry
> from industrial equipment into explainable assessments and recommendations.
> Everything you're about to see is running live: a physics-based simulator,
> a real ingestion pipeline, and a deterministic reasoning engine — no
> hardcoded UI states."

## 2. Architecture overview (0:20–1:00)

**On screen:** README architecture diagram, or narrate over the dashboard.

> "Telemetry flows from a simulated fuel-cell plant over MQTT, through a
> bridge into a FastAPI ingestion service, and lands in TimescaleDB. Every
> observation triggers a reasoning job on a background worker. The worker
> runs a seven-stage deterministic pipeline — signal extraction, evidence
> generation, hypothesis, assessment, confidence, explanation, planning —
> and persists the result as an immutable reasoning record. The dashboard
> reads that through a digital twin read model and gets pushed live updates
> over Server-Sent Events."

*(Cut point if trimming to 3 minutes: compress to two sentences — MQTT → API
→ worker → dashboard, deterministic pipeline, no ML.)*

## 3. Simulator (1:00–1:30)

**On screen:** fleet strip at the top of the dashboard, all four assets.

> "Plant Alpha is four PEM fuel-cell stacks, modeled with first-order-lag
> physics — not random noise. Right now they're all cycling through normal
> load. In a moment, the simulator injects a real fault into stack one's
> physics model: degrading cooling efficiency. That's not a scripted UI
> state — it's a change to the simulated plant that the reasoning engine
> has to detect on its own."

## 4. Dashboard walkthrough (1:30–2:15)

**On screen:** click through fleet strip, asset status bar, health/risk/confidence tiles.

> "Selecting an asset shows its operational state: health score, risk level,
> and decision confidence, each with a primary driver — the reasoning
> engine's stated reason for that assessment. This isn't a status flag someone
> set; it's computed from the same evidence you can inspect in the
> investigation panel."

## 5. Investigation workflow (2:15–3:15)

**On screen:** wait for (or already be at) the fault window; show the active
alert banner, Recommended Action panel, and the investigation timeline.

> "Once the fault crosses a threshold, a prioritized recommendation appears
> — priority, category, and numbered operator steps. This is where the
> operator lifecycle comes in: acknowledge, start investigating, resolve.
> Each transition is an append-only record, not a status field that gets
> overwritten — you can see who acted, when, and why."

**Action:** select an operator, click **Acknowledge**, then **Start
investigating**. Show the status badge and actor line updating live.

*(Cut point if trimming to 3 minutes: do only "Acknowledge," skip
"Start investigating.")*

## 6. Reasoning (3:15–3:50)

**On screen:** click a timeline event, show Event Context and the evidence/
alternative-hypotheses panel in the investigation rail.

> "Every recommendation traces back to evidence: which measurements
> contributed, their weights, and alternative hypotheses the engine
> considered and rejected — like sensor drift instead of a real fault. This
> is the explainability guarantee: nothing here is a black-box score."

## 7. Closing (3:50–4:00)

**On screen:** back to the fleet overview.

> "That's the full loop: live ingestion, a real physics-based fault,
> deterministic explainable reasoning, and an auditable operator response —
> running as one system, not a demo harness. Code and docs are on GitHub."

---

## Resolved risk — healthy peers misreading WARNING/CRITICAL

Two related issues were found and fixed during v1.0 hardening, both outside
the core reasoning pipeline and the `DecisionPlanner`; see
[Demo Environment → Known limitations](../platform/demo-environment.md#known-limitations)
for the full root-cause writeup:

- All four fleet assets reaching `CRITICAL` simultaneously during
  `cooling_degradation`, not just the intended fault target — a calibration
  gap in `VariationDetector`/`TrendDetector` and an unbounded observation
  window (fixed via `ReasoningSessionConfig.observation_window` and a
  `TrendDetector` rewrite).
- A smaller residual: individual healthy peers transiently flipping to
  `WARNING`/`CRITICAL` (a stale `OPEN` notification, since notifications
  don't auto-clear when health recovers) at session startup and periodically
  through a session — a minimum-history floor missing from `TrendDetector`
  and a separate, previously-uncalibrated legacy trend algorithm in the
  backend platform layer (fixed via a shared minimum-sample floor and a
  wider window).

Verified on a fresh clean stack: all four assets read `NORMAL` (health score
90) with no notification present, holding for the duration of a full
`normal_operation` window before `cooling_degradation` starts.

**Before recording:** still do a dry run of the exact window you intend to
shoot — that's good practice regardless of fix status — and confirm the
fleet strip matches the "only one stack faults" narrative this script is
built around. If it doesn't, this needs maintainer triage before the session
is recorded.
