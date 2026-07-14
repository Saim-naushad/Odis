# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project philosophy

ODIS is treated as a flagship engineering portfolio project. The architecture is intentionally stable — the project is no longer optimizing for feature count. Every change should improve one or more of: resume value, demo quality, GitHub presentation, industrial realism, or engineering depth. Avoid speculative refactors; favor small, focused pull requests over large ones.

The engineering principles that shape the reasoning core — keep the domain model simple, prefer explicit reasoning over clever abstractions, preserve append-only semantics, separate evidence/signal/assessment/decision, avoid complexity before repeated patterns justify it, no AI/ML in the core reasoning pipeline unless explicitly scoped — are the full authority in [CONTRIBUTING.md](CONTRIBUTING.md#philosophy). They are not style preferences; they protect the reasoning model as the system grows. Read that section before touching `src/domain/` or `src/application/`, and keep it in sync with this file if either changes.

## Workflow

Before implementing anything non-trivial:

1. Explain why it's worth building (tie it to one of the five portfolio criteria above).
2. Identify architectural impact — which layer(s)/subsystem(s) it touches and whether it respects the boundaries described below.
3. Define scope explicitly — what's in, what's out.
4. Implement only that scope. Do not bundle unrelated cleanups into the same change.

ODIS grows in milestones, not large feature drops — typically one architectural capability per PR (a domain entity, a detector, a use case, a test foundation, a docs pass). Update `docs/` alongside the code whenever a pipeline stage, layer responsibility, or extension point changes; update the root `README.md` only when user-facing capabilities or setup instructions change.

## Validation checklist

Run before considering any change complete:

```bash
ruff check .
mypy src backend tests
pytest
```

Frontend changes additionally require, from `frontend/`:

```bash
npm run lint
npm run build
npm test
```

For UI-affecting changes, run the app and exercise the affected flow in the browser — don't rely on type checks alone to claim a frontend feature works. Pre-commit and CI mechanics (what runs automatically on commit vs. what you must run yourself) are documented in [CONTRIBUTING.md](CONTRIBUTING.md#development-setup) — see there rather than duplicating that narrative here.

## Coding standards

Full coding guidelines — immutable domain entities, composition over inheritance, thin application orchestration, no hidden side effects, type-annotation requirements — are the full authority in [CONTRIBUTING.md](CONTRIBUTING.md#coding-guidelines). Keep both files consistent by editing CONTRIBUTING.md first.

Facts specific to this codebase's tooling, not covered there:

- MyPy enforces `disallow_untyped_defs` on `domain.*`, `application.*`, and `backend.*` (see `[tool.mypy.overrides]` in `pyproject.toml`). Ruff line length is 88; isort groups are `application`, `backend`, `domain`, `infrastructure`, `odis`, `tests` as first-party.
- **Tests as executable specifications** — use `tests/builders.py` (e.g. `build_observation_sequence([32, 35, 38])`) to express intent concisely rather than verbose manual setup. Tests marked `integration` require the Docker Compose services to be running.

## Architecture assumptions

ODIS has two concentric layers: a transport- and persistence-agnostic **reasoning engine** (`src/`), and a **platform** (`backend/`, `frontend/`, `infra/`, `k8s/`) that hosts it. `backend/app/application/*` imports directly from `src/application`/`src/domain` (resolved via `pyproject.toml`'s `package-dir = {"" = "src"}`) — the backend does not duplicate reasoning logic, it orchestrates and persists it.

**Reasoning engine (`src/`)** — clean-architecture layering, dependencies point inward only:
- `src/domain/` — entities (`Observation`, `OperationalSituation`, `DecisionContext`, `DecisionPlan`, `Action`, `Outcome`), value objects, events, repository interfaces. No dependency on any other layer.
- `src/application/` — `ReasoningSession` runs a fixed 7-stage pipeline (`src/application/reasoning/`): SignalExtraction → EvidenceGeneration → Hypothesis → Assessment → Confidence → Explanation → Planning. Detectors (`TrendDetector`, `VariationDetector`, `CorrelationDetector`/`ContradictionDetector`) are deliberately simple and deterministic — no ML.
- `src/application/profiles/` — `OperationalProfile` subclasses (default vs. `FuelCellOperationalProfile`) inject domain-specific relationship rules and expectation logic *without* changing core detectors, stages, or the planner.
- `src/odis/` — the public library surface (`odis` package + `odis demo ...` CLI). Import from `odis`, not internal `domain`/`application` modules, when writing examples or external-facing code.
- `DecisionPlanner` (`src/application/decision_planner.py`) matches on assessment *text* (substring/casefold) — a known, intentional placeholder, not a production policy engine. Assessment wording in `operational_situation_assessor.py` and the planner's matching must be changed together.

**Backend platform (`backend/app/`)** — FastAPI API + background worker sharing one composition root (`bootstrap_application_runtime`, wired in `bootstrap.py`). Patterns used throughout: Unit of Work (`SqlAlchemyUnitOfWork`), Repository, an in-process `DomainEventBus`, and a transactional Outbox (`OutboxDispatcher`) for at-least-once delivery of integration events to Kafka. The worker polls a DB-backed `ReasoningJobQueue` and invokes the `src/` reasoning engine via `ObservationService`. `DigitalTwinService` is a read-model composer only — it must not recompute operational state, only assemble it from `MonitoringService` plus forecasts, cached in Redis with event-driven invalidation.

**Simulator (`backend/simulator/`)** — "Plant Alpha," a 4-stack PEM fuel-cell digital twin using first-order-lag physics (not RNG), so subsystems move coherently under fault scenarios (cooling degradation, hydrogen supply issue, sensor anomaly, recovery). Publishes over MQTT (production path: Mosquitto → `backend/mqtt_bridge/` → `POST /observations`) or HTTP directly. Treat it strictly as an external boundary — it never writes to repositories directly.

**Frontend (`frontend/src/`)** — single-page React 19 + TypeScript + Vite console (no router). State is entirely React Query, with `/monitoring/events` SSE pushing targeted cache invalidation and a 60s poll as fallback only when SSE is disconnected. `MonitoringDashboard.tsx` composes the whole layout from `components/monitoring/*`.

**Data flow**: `PlantAlphaSimulator → MQTT (Mosquitto) → mqtt-bridge → FastAPI → TimescaleDB`, worker picks up reasoning jobs asynchronously and persists reasoning artifacts, dashboard reads via REST and SSE.

## Commands

**Reasoning library only (no Docker):**
```bash
pip install -e ".[dev]"
pre-commit install
odis demo all              # or: python examples/run_demo.py
```

**Full platform (Docker Compose):**
```bash
docker compose --profile demo up --build -d   # full stack + Plant Alpha simulator
docker compose up --build -d                  # platform without the demo profile
```

**Hybrid (infra in Docker, apps on host):**
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis kafka prometheus grafana
export DATABASE_URL=postgresql+psycopg://odis:odis@localhost:5432/odis
alembic upgrade head
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
# in another terminal:
python -m backend.app.worker_main
cd frontend && npm run dev   # proxies /api to localhost:8000
```

**Single test / targeted runs:**
```bash
pytest tests/application/test_reasoning_session.py
pytest tests/application/test_reasoning_session.py::test_specific_case
pytest -k "trend_detector"
pytest -m "not integration"   # skip tests requiring docker compose services
```
