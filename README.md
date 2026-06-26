# ODIS

ODIS is an operational reasoning platform that transforms measurements from physical assets into explainable operational decisions.

Industrial systems generate continuous observations — temperature, pressure, flow rate, voltage, and more. Raw measurements are not decisions. ODIS provides a structured pipeline that separates **evidence**, **signals**, **assessments**, and **recommendations** so operational reasoning remains traceable, deterministic, and auditable.

This repository is an architectural foundation, not a production deployment. It demonstrates how operational reasoning can be modeled explicitly rather than buried in ad hoc scripts or opaque automation.

## Why ODIS exists

Operational teams need more than dashboards. They need to understand:

- What was observed
- What pattern was detected
- How the situation was assessed
- Why a particular recommendation was made

ODIS encodes that reasoning chain as immutable, append-only records. Each stage produces a snapshot that can be replayed, compared, and extended — without rewriting history when understanding improves.

The design prioritizes **clarity over cleverness**, **deterministic logic over black-box automation**, and **architecture that generalizes across industries** (energy, manufacturing, mining, infrastructure) without hardcoding domain-specific rules in the core model.

## Reasoning pipeline

```
Observation
    ↓
Detected Trend
    ↓
Operational Situation
    ↓
Decision Context
    ↓
Decision Plan
```

| Stage | Role |
|-------|------|
| **Observation** | An immutable measurement recorded from the environment — what was measured, on which asset, when, and in what units. |
| **Detected Trend** | A deterministic signal derived from a sequence of observations. The current implementation compares first and last values after timestamp ordering. |
| **Operational Situation** | An assessment of operational conditions derived from evidence and signal. Records which observations informed the assessment and a human-readable interpretation. |
| **Decision Context** | A frozen snapshot of everything the planner knew when reasoning began — goal, situation reference, and assessment. |
| **Decision Plan** | A recommendation with priority, action, and justification. Immutable once generated. |

Evidence, signal, assessment, and decision are intentionally separate. Collapsing them would make reasoning harder to audit and extend.

## Current capabilities

ODIS currently supports:

- **Heatwave reasoning** — rising measurements produce an increasing trend, elevated assessment, and high-priority investigation recommendation
- **Stable operations reasoning** — steady conditions produce a stable trend and continue-monitoring recommendation
- **Oscillating scenario** — demonstrates a known limitation where significant mid-sequence variation is classified as stable when first and last values match
- **Deterministic explainable recommendations** — every plan includes an explicit justification string; no AI or machine learning is involved

Run the unified demonstration to see all three scenarios:

```bash
python examples/run_demo.py
```

Individual walkthroughs are also available under `examples/`.

## Running the project

**Requirements:** Python 3.11+

**Installation:**

```bash
git clone <repository-url>
cd Odis
pip install -e ".[dev]"
```

**Run the unified demo:**

```bash
python examples/run_demo.py
```

**Run tests:**

```bash
pytest
```

For a single suite:

```bash
pytest tests/application/      # component specifications
pytest tests/integration/      # end-to-end pipeline specifications
```

## Project architecture

```
src/
├── domain/           # Entities, value objects, events, repository interfaces
├── application/      # Use cases, detectors, assessors, planners
├── infrastructure/   # Reserved for future persistence and adapters
└── shared/           # Reserved for cross-cutting utilities

examples/             # Executable operational walkthroughs
tests/                # Behavioral specifications and test builders
```

### Domain layer (`src/domain/`)

The core model. Immutable entities (`Asset`, `Observation`, `OperationalSituation`, `DecisionContext`, `DecisionPlan`, and others), value objects (`MeasurementType`, `Priority`, `TrendDirection`), domain events, and repository interfaces. No dependency on application or infrastructure code.

### Application layer (`src/application/`)

Orchestrates domain concepts without embedding domain invariants incorrectly:

- `TrendDetector` — signal detection from observation sequences
- `OperationalSituationAssessor` — transforms evidence and signal into operational assessment
- `create_decision_context` — snapshots planner inputs
- `DecisionPlanner` — produces recommendations from context

### Examples (`examples/`)

Executable demonstrations that walk through complete operational scenarios. These are architectural proofs, not production services.

### Tests (`tests/`)

Behavioral specifications for components and the full pipeline. Reusable builders in `tests/builders.py` express test intent as value sequences rather than verbose object construction.

## Current limitations

ODIS is early-stage. Be aware of the following:

- **Single-signal reasoning** — only trend detection is implemented. Variability, instability, and anomaly patterns are not yet modeled as separate signals.
- **Placeholder planning rules** — the `DecisionPlanner` uses generic substring matching on assessment text. These are scaffolding, not production policy.
- **No persistence** — repository interfaces exist, but no storage implementation is wired. All demos and tests run in memory.
- **No real telemetry ingestion** — observations are constructed synthetically. There is no connector to SCADA, IoT platforms, or time-series databases.
- **No actions or outcomes loop** — `Action` and `Outcome` entities exist in the domain model but are not yet part of the executable pipeline.

## Roadmap

Planned direction (not committed deliverables):

- **Multi-signal reasoning** — additional detectors (e.g., variability, rate-of-change) composed alongside trend analysis
- **Richer operational assessments** — assessments informed by multiple signals and operational goals
- **Historical replay** — reconstruct decision chains from append-only records
- **Production integrations** — persistence, telemetry ingestion, and industry-specific planning strategies behind stable interfaces

## Design principles

- **Append-only history** — change is recorded as new immutable snapshots, not in-place mutation
- **Separation of concerns** — evidence, signal, assessment, and decision remain distinct
- **Deterministic reasoning** — same inputs produce the same outputs; no AI or ML in the current pipeline
- **Industry-agnostic core** — the domain model avoids hardcoded thresholds, taxonomies, or sector-specific terminology

---

ODIS is a reasoning architecture under active development. Run `python examples/run_demo.py` to see what it does today.
