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

## Known risk — verify before recording

During a validation run of this script (2026-07-14), all four fleet assets
reached `CRITICAL` health simultaneously during the `cooling_degradation`
phase, not just the intended fault target (`fuel-cell-stack-01`). Traced to
`backend/app/application/operational_state_engine.py`: `health_score` applies
a flat `priority_penalty` (45 points for `"high"`) driven by
`DecisionPlanner`'s output, and the planner is the documented placeholder
(substring/casefold matching on assessment text — see `README.md`'s
"Placeholder planning rules" limitation and `CLAUDE.md`). It isn't a new
regression — the underlying limitation is already disclosed — but the
demo-visible consequence (three "healthy peer" assets reading CRITICAL
alongside the actual fault) undercuts the "only one stack faults" narrative
this script is built around.

**Before recording:** do a dry run of the exact `cooling_degradation` window
you intend to shoot and confirm `fuel-cell-stack-02/03/04` show
`NORMAL`/`WARNING`, not `CRITICAL`, in the fleet strip. If they don't, this
needs maintainer triage before the session is recorded — narrating around a
fleet strip that shows every asset as critical will read as a bug on camera,
even though the reasoning trace behind it is real and correctly evidenced.
