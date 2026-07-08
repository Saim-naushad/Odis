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

## Domain Profiles

ODIS ships with multiple **operational profiles**:

- **Default educational profile** — the baseline profile used in most examples.
- **Fuel cell profile** — a representative profile that demonstrates how to add domain-specific operational knowledge through configuration.

Profiles are **extension points**: they package domain-specific policies (for example, which cross-measurement relationships are worth evaluating) without changing detectors, planners, or the core reasoning pipeline.

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

## Local development (Monitoring Dashboard MVP)

Start PostgreSQL:

```bash
docker compose up -d
```

Set `DATABASE_URL` (copy `.env.example` to `.env`, or export it in your shell):

```bash
export DATABASE_URL=postgresql+psycopg://odis:odis@localhost:5432/odis
```

Run migrations:

```bash
alembic upgrade head
```

Start backend:

```bash
python -m uvicorn backend.app.main:app --reload
```

Start frontend:

```bash
cd frontend
npm install
npm run dev
```

## Versioning

- **Current version**: `0.1.0`
- **Changelog**: `CHANGELOG.md`
- **Policy**: Future releases intend to follow Semantic Versioning (SemVer).

## Public API

After installation, import from the package root:

```python
from odis import (
    Asset,
    Location,
    MeasurementType,
    Observation,
    OperationalGoal,
    ReasoningSession,
)

asset = Asset(
    id="pump-01",
    name="Pump P-07",
    type="centrifugal_pump",
    location=Location(identifier="cooling-loop-beta"),
)
session = ReasoningSession()
result = session.run(goal, observations)
```

Exported domain entities, value objects (`Location`, `MeasurementType`, `Priority`,
`TrendDirection`, `VariationLevel`), detectors, assessors, planners, and recording
use cases are available from ``odis``. Internal modules such as ``application``,
``domain``, and ``infrastructure`` remain importable for development but are not
the supported public surface.

## Command-line interface

The recommended way to explore ODIS after installation:

```bash
pip install -e ".[dev]"
odis demo all
```

Individual walkthroughs:

```bash
odis demo heatwave
odis demo stable
odis demo oscillating
odis demo fuel-cell
```

Run reasoning from CSV:

```bash
odis demo csv
```

This is the first demonstration that loads **real observations from an ingestion adapter**
(`CsvObservationSource`) rather than constructing observations in code.

Run `odis --help` for available commands.

You can also run demonstrations directly:

```bash
python examples/run_demo.py
```

**Run tests:**

```bash
pytest
```

**Run quality checks:**

```bash
ruff check .
mypy src tests
```

These checks run automatically on every push and pull request via GitHub Actions.

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

### Architecture diagrams

For version-controlled diagrams of the current implementation, see
[`docs/architecture-diagrams.md`](docs/architecture-diagrams.md).

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

- **Limited multi-signal reasoning** — trend and variation detection are implemented; additional signal types (e.g., anomaly patterns, rate-of-change) are not yet modeled as separate signals.
- **Placeholder planning rules** — the `DecisionPlanner` uses generic substring matching on assessment text. These are scaffolding, not production policy.
- **In-memory persistence only** — repositories are implemented as in-memory stores. There is no durable database, message bus, or external storage adapter.
- **Limited telemetry ingestion** — a CSV observation source is available, but there are no connectors to SCADA, IoT platforms, or time-series databases.
- **No real-world actions or feedback loop** — `Action` and `Outcome` records are created in the executable pipeline, but they are not yet wired to external execution systems or closed-loop learning.

## Roadmap

Planned direction (not committed deliverables):

- **Richer multi-signal reasoning** — additional detectors (e.g., anomaly and rate-of-change signals) composed alongside existing trend and variation analysis
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
