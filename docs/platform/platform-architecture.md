# ODIS Platform Architecture

This document is the canonical reference for how ODIS is structured as a production system. It describes the industrial platform that wraps the completed Reasoning Engine v1 and guides every remaining implementation effort.

This is an evolving platform architecture document, not an RFC. It will grow alongside implementation.

For reasoning design and codebase organization, see [Architecture](../architecture.md). For research foundations, see [Research](../research/).

---

## Purpose

ODIS has completed **Reasoning Engine v1** — the deterministic, explainable operational reasoning pipeline documented in the architecture and research layers. Phase 2 shifts the project from designing reasoning architecture to building a **deployable industrial software platform**.

From this point forward:

- **The reasoning engine is one subsystem of ODIS**, not the whole product. It transforms operational evidence into structured assessments and recommendations. It remains the intellectual core of the platform, but it operates within a larger system that ingests telemetry, persists history, exposes APIs, and presents results to operators.

- **ODIS is an industrial operational intelligence platform** — software designed for continuous operation in industrial environments where reliability, traceability, and explainability matter more than novelty.

- **The project is demonstrated using PEM fuel cell systems** as a representative industrial domain. Fuel cell operational knowledge is packaged as a domain profile; the platform architecture itself is domain-agnostic.

- **Deterministic reasoning is the platform's differentiator, not its entirety.** Explainable, auditable reasoning distinguishes ODIS from threshold-based alerting and opaque automation. The platform must also deliver ingestion, persistence, APIs, dashboards, and deployment infrastructure that industrial teams expect from production software.

---

## System Vision

ODIS is an **industrial platform**, not a Python library imported into ad hoc scripts.

The vision is software that:

- **Deploys in industrial environments** — on-premises, at the edge, or in cloud infrastructure — and runs continuously alongside operational equipment.

- **Delivers operational intelligence** — not just data visualization, but structured assessments that explain what was observed, what patterns were detected, what the situation means, and why a recommendation was made.

- **Preserves explainable reasoning** — every assessment and recommendation remains traceable to evidence. Operators and engineers can audit the reasoning chain without reverse-engineering a black box.

- **Scales through a modern backend architecture** — services with clear boundaries, APIs as integration points, and persistence that supports historical replay and longitudinal analysis.

- **Follows modern software engineering practices** — typed Python, automated testing, linting, CI/CD, containerized deployment, and observability hooks for production operation.

The platform turns the reasoning engine from a library invoked in examples into a **running system** that operators interact with every day.

---

## High-Level Platform Architecture

The platform connects industrial equipment, ingestion pipelines, backend services, persistence, reasoning, and operator-facing interfaces into a cohesive system.

### Major components

| Component | Role |
|-----------|------|
| **Industrial Equipment** | Physical assets (e.g., PEM fuel cell stacks) that generate operational measurements |
| **Fuel Cell Simulator** | Development and demonstration substitute for physical equipment; produces realistic telemetry streams |
| **MQTT / OPC UA Ingestion** | Industrial protocol adapters that receive telemetry and forward it to the platform |
| **FastAPI Platform** | HTTP API layer — the primary integration boundary for all platform consumers |
| **Reasoning Engine** | Deterministic operational reasoning subsystem (Reasoning Engine v1) |
| **PostgreSQL** | Durable persistence for observations, reasoning artifacts, and platform state |
| **React Dashboard** | Operator-facing web interface for monitoring, assessments, and historical views |
| **External Users** | Operators, engineers, and integrators who consume platform APIs and dashboards |

### Architecture overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INDUSTRIAL ENVIRONMENT                            │
│                                                                             │
│   ┌──────────────────┐         ┌──────────────────┐                       │
│   │ Industrial       │         │ Fuel Cell        │                       │
│   │ Equipment        │         │ Simulator        │                       │
│   │ (PEM stacks,     │         │ (dev / demo)     │                       │
│   │  sensors)        │         │                  │                       │
│   └────────┬─────────┘         └────────┬─────────┘                       │
│            │                            │                                   │
│            │    MQTT / OPC UA            │                                   │
│            └────────────┬───────────────┘                                   │
│                         ▼                                                   │
│              ┌─────────────────────┐                                        │
│              │   Ingestion Layer   │                                        │
│              │  (MQTT subscriber,  │                                        │
│              │   OPC UA client)    │                                        │
│              └──────────┬──────────┘                                        │
└─────────────────────────┼───────────────────────────────────────────────────┘
                          │ HTTP / internal API
                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ODIS PLATFORM (FastAPI)                             │
│                                                                             │
│   ┌─────────────┐    ┌─────────────────┐    ┌─────────────────────────┐   │
│   │  API Layer  │───▶│  Persistence    │◀──▶│  PostgreSQL             │   │
│   │  (REST)     │    │  (SQLAlchemy)   │    │                         │   │
│   └──────┬──────┘    └─────────────────┘    └─────────────────────────┘   │
│          │                                                                  │
│          ▼                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Reasoning Engine (v1)                            │   │
│   │  Observation → Signal → Assessment → Decision Context → Plan       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ HTTP / WebSocket
                               ▼
                    ┌─────────────────────┐
                    │   React Dashboard   │
                    │   (TypeScript)      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   External Users    │
                    │   (operators,       │
                    │    engineers)       │
                    └─────────────────────┘
```

### Data plane vs. control plane

```
  TELEMETRY PATH (data plane)                REASONING PATH (intelligence plane)
  ───────────────────────────                ───────────────────────────────────

  Equipment ──▶ Ingestion ──▶ API ──▶ DB     API ──▶ Reasoning ──▶ Assessment ──▶ DB
                                                                    │
                                                                    ▼
                                                              Dashboard
```

The platform separates **moving data** (ingestion, persistence) from **deriving intelligence** (reasoning, assessment). Both paths converge in persistence and are surfaced through the API and dashboard.

---

## Platform Responsibilities

Each subsystem has a distinct responsibility. Overlap is intentional at API boundaries; duplication of logic across subsystems is not.

### Ingestion

**Receives operational telemetry from industrial sources and delivers it to the platform.**

- Subscribes to MQTT topics or connects to OPC UA servers
- Normalizes incoming measurements into platform observation records
- Forwards observations to the API layer for validation and persistence
- Remains **replaceable** — swapping MQTT for Kafka or adding new protocol adapters must not require changes to reasoning logic

Ingestion exists because industrial equipment speaks industrial protocols. The platform must meet equipment where it is, not require equipment to speak HTTP.

### API

**The primary integration boundary for all platform consumers.**

- Accepts observations from ingestion services
- Triggers reasoning when appropriate
- Exposes assessments, reasoning history, and operational state to the dashboard and external integrators
- Enforces request validation, error handling, and API versioning conventions

The API exists because every subsystem — ingestion, reasoning, frontend, third-party integrations — should integrate through a stable, documented contract rather than shared database access or direct library imports.

### Monitoring boundary

**Monitoring endpoints provide read-only access to persisted reasoning history and debugging data.**

- Serve dashboards and operator tooling without exposing persistence internals
- Offer stable contracts for reasoning artifacts (situations, assessments, plans, traces)
- Keep orchestration in application services; routers remain thin
- Avoid auth, pagination frameworks, and complex filtering DSLs until explicitly required

Representative endpoints:

- `GET /monitoring/assets`
- `GET /monitoring/assets/{asset_id}/latest`
- `GET /monitoring/assets/{asset_id}/history`
- `GET /monitoring/runs/{run_id}`

### Reasoning

**Transforms operational evidence into structured assessments and recommendations.**

- Executes the deterministic reasoning pipeline (Reasoning Engine v1)
- Applies domain profiles (e.g., fuel cell operational knowledge)
- Produces immutable reasoning artifacts: situations, decision contexts, decision plans
- Remains **independent** of messaging technologies, databases, and UI frameworks

Reasoning exists because raw measurements are not decisions. The platform's value is explainable operational intelligence, not data relay.

### Persistence

**Durable storage for all platform state and reasoning artifacts.**

- Stores observations, reasoning runs, assessments, and platform metadata
- Supports historical queries and replay
- Provides the foundation for longitudinal analysis and audit trails

Persistence exists because operational intelligence must survive process restarts, support historical analysis, and enable reasoning replay from stored evidence.

### Frontend

**Operator-facing interface for monitoring and understanding operational state.**

- Presents current assessments, reasoning traces, and historical trends
- Communicates exclusively through platform APIs
- Never accesses databases or reasoning internals directly

The frontend exists because operators need more than API responses — they need a purpose-built interface for understanding what the system observed, assessed, and recommended.

### Deployment

**Packaging, orchestration, and runtime infrastructure for the platform.**

- Docker containers for each service
- Docker Compose for local development and initial deployment
- Environment configuration, health checks, and service discovery
- Future path to Kubernetes without changing subsystem responsibilities

Deployment exists because industrial software must run reliably in real environments, not only in developer notebooks.

---

## End-to-End Data Flow

The lifecycle of operational data through the platform:

```
Industrial Equipment
        │
        │  measurements (temperature, pressure, voltage, flow, ...)
        ▼
    Ingestion
        │
        │  normalized observations
        ▼
       API
        │
        │  validated, accepted observations
        ▼
   Persistence
        │
        │  stored observations
        ▼
    Reasoning
        │
        │  signals, assessments, recommendations
        ▼
   Assessment
        │
        │  structured operational intelligence
        ▼
   Persistence
        │
        │  stored reasoning artifacts
        ▼
    Dashboard
        │
        │  presented to operators
        ▼
  External Users
```

### Conceptual stages

1. **Industrial equipment** generates continuous measurements — the raw evidence of operational state.

2. **Ingestion** receives telemetry through industrial protocols and translates it into platform observations.

3. **API** validates incoming data, acknowledges receipt, and routes observations to persistence.

4. **Persistence** stores observations as immutable records, establishing the evidence foundation.

5. **Reasoning** reads stored observations (or receives them through the application pipeline), applies domain profiles, and executes the deterministic reasoning chain.

6. **Assessment** is the output of reasoning — operational situations, structured interpretations, and decision plans.

7. **Persistence** stores reasoning artifacts alongside the observations that produced them, preserving the full audit trail.

8. **Dashboard** queries the API for current state and historical reasoning, presenting results to operators.

This flow is conceptual. Implementation details — endpoint shapes, table schemas, message formats — are defined in subsequent implementation work.

---

## Service Boundaries

Platform subsystems are grouped by responsibility. Boundaries exist to keep the system maintainable, testable, and evolvable.

### What belongs together

| Boundary | Responsibilities grouped |
|----------|-------------------------|
| **Reasoning subsystem** | Signal detection, assessment, planning, profile evaluation, reasoning trace generation |
| **API subsystem** | HTTP routing, request validation, orchestration of persistence and reasoning calls |
| **Ingestion subsystem** | Protocol adapters, message normalization, delivery to API |
| **Persistence subsystem** | Database access, migrations, repository implementations |
| **Frontend subsystem** | UI components, API client, operator workflows |

### What must remain isolated

**Reasoning must remain independent from messaging technologies.**

The reasoning engine consumes observations — it does not subscribe to MQTT topics or parse OPC UA node IDs. Ingestion translates industrial protocols into observations; reasoning never knows which protocol delivered them. This allows MQTT to be replaced with Kafka, or OPC UA to be added, without touching reasoning logic.

**Reasoning must remain independent from persistence.**

The reasoning engine operates on domain objects. Repository interfaces define persistence contracts; concrete implementations live in infrastructure. Reasoning can be tested in memory without a database. Persistence technology can change without rewriting assessment logic.

**APIs are the primary integration boundary.**

Ingestion talks to the API, not to the database. The dashboard talks to the API, not to reasoning internals. External integrators talk to the API, not to ingestion services. Every cross-subsystem interaction flows through documented HTTP contracts.

**The frontend never talks directly to databases.**

All data access flows through the API. This preserves a single source of truth for authorization (future), caching, and data shaping. The frontend is a consumer, not a data layer.

**Ingestion should remain replaceable.**

New protocol adapters are added by implementing the ingestion contract, not by modifying the API or reasoning subsystems. The ingestion layer is a plugin surface, not a monolith.

### Boundary diagram

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Ingestion   │     │     API      │     │   Frontend   │
│              │────▶│              │◀────│              │
│  (protocols) │     │  (HTTP)      │     │  (React)     │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                   ┌────────┴────────┐
                   │                 │
                   ▼                 ▼
            ┌─────────────┐   ┌─────────────┐
            │ Persistence │   │  Reasoning  │
            │             │   │             │
            │ (PostgreSQL)│   │  (engine)   │
            └─────────────┘   └─────────────┘
                   │                 │
                   └────────┬────────┘
                            │
                   Reasoning reads/writes
                   through repository interfaces,
                   not direct DB or messaging access
```

---

## Backend Persistence Architecture

The platform backend establishes persistence as an infrastructure concern under `backend/app/infrastructure/`. SQLAlchemy and Alembic live exclusively in this layer — the reasoning engine in `src/` never imports them.

### Package layout

```
backend/app/infrastructure/
  database/
    base.py          # SQLAlchemy DeclarativeBase for ORM models
    session.py       # Engine and session factory creation
    models/          # SQLAlchemy ORM models (infrastructure only)
    mappers/         # Domain ↔ ORM mapping functions
  repositories/
    protocols.py     # PlatformRepository marker protocol
    base.py          # SqlAlchemyRepository base class
    observation_repository.py  # SQLAlchemy ObservationRepository
```

Alembic migrations are configured at the repository root (`alembic/`, `alembic.ini`) and load the database URL from application settings (`DATABASE_URL`).

### Persistence boundary

| Layer | Location | Responsibility |
|-------|----------|----------------|
| **Domain contracts** | `src/domain/repositories/` | Abstract repository interfaces (observations, situations, plans, etc.) |
| **Reasoning engine** | `src/` | Operates on domain objects; uses in-memory repositories for tests |
| **Platform infrastructure** | `backend/app/infrastructure/` | SQLAlchemy engine, sessions, ORM models, concrete repository implementations |
| **API orchestration** | `backend/app/api/` | FastAPI dependencies inject request-scoped sessions; routes call application services |

The reasoning engine defines **what** to persist through domain repository interfaces. The platform backend defines **how** to persist through SQLAlchemy-backed implementations that satisfy those interfaces. This separation keeps assessment logic testable without a database and allows persistence technology to evolve independently.

### Repository pattern

Entity repositories:

1. Implement a domain repository interface from `src/domain/repositories/`
2. Subclass `SqlAlchemyRepository` for session management
3. Map between domain entities and ORM models within the infrastructure layer

`SqlAlchemyObservationRepository` is the first concrete implementation. It satisfies the domain `ObservationRepository` contract with `save`, `get`, and `list`. Observations are immutable — no update or delete operations are exposed.

### Observation persistence

Observations are the first entity persisted by the platform. They are the evidence foundation for reasoning: every assessment traces back to stored measurement records.

| Domain field | ORM column | Notes |
|--------------|------------|-------|
| `id` | `id` | Primary key |
| `asset_id` | `asset_id` | Indexed for asset-scoped queries |
| `timestamp` | `timestamp` | Timezone-aware `DateTime` |
| `measurement_type.name` | `measurement_type_name` | Value object flattened to string |
| `value` | `value` | `float` |
| `unit` | `unit` | Measurement unit string |

Mapping is explicit and isolated in `backend/app/infrastructure/database/mappers/observation.py`. ORM models never leave the infrastructure layer — repository methods accept and return domain `Observation` entities.

The initial Alembic migration (`b8265a976460`) creates the `observations` table. The migration `c4f1a8d29e10` adds reasoning artifact tables (`reasoning_runs`, `operational_situations`, `decision_contexts`, `decision_plans`, `reasoning_run_indexes`, `structured_assessments`, `reasoning_traces`).

### Repository responsibilities

| Method | Behavior |
|--------|----------|
| `save(observation)` | Insert a new observation; reject duplicate IDs |
| `get(id)` | Return the domain observation or `None` |
| `list()` | Return all persisted observations as domain objects |
| `list_by_asset(asset_id)` | Return observations for one asset ordered by `timestamp`, then `id` |

The reasoning engine depends only on the domain `ObservationRepository` interface. It can run with `InMemoryObservationRepository` in tests or `SqlAlchemyObservationRepository` in production — no changes to reasoning logic are required.

### Observation API

The first production API vertical slice exposes observation persistence over HTTP. It completes the path from API clients through application services and repositories to PostgreSQL (or SQLite in tests), and automatically executes reasoning when sufficient asset evidence is available.

#### Endpoints

| Method | Path | Status | Behavior |
|--------|------|--------|----------|
| `POST` | `/observations` | `201 Created` | Validate payload, persist observation, return serialized record |
| `GET` | `/observations` | `200 OK` | Return all observations ordered by `timestamp`, then `id` |
| `GET` | `/observations/{id}` | `200 OK` / `404 Not Found` | Return one observation or a not-found error |

OpenAPI metadata (summaries, response models, and examples) is generated from the Pydantic schemas and route declarations.

#### Request flow

```
HTTP client
    │
    ▼
FastAPI router (backend/app/api/routers/observations.py)
    │  validates request / maps HTTP status codes
    ▼
ObservationService (backend/app/application/observation_service.py)
    │  coordinates use case; works with domain entities
    ▼
ObservationRepository (domain interface)
    │
    ▼
SqlAlchemyObservationRepository (backend/app/infrastructure/repositories/)
    │  maps domain ↔ ORM
    ▼
PostgreSQL
```

Routers never call repositories directly. Dependency injection wires each request-scoped SQLAlchemy session into a repository implementation, then into an application service:

```
Depends(get_db_session)
    → Depends(get_observation_repository)
        → Depends(get_observation_service)
```

#### API boundary

The HTTP layer exposes dedicated Pydantic schemas (`ObservationCreate`, `ObservationResponse`) in `backend/app/api/schemas/observation.py`. SQLAlchemy models and domain entities do not cross this boundary:

- **Inbound:** `ObservationCreate` validates the JSON payload and translates it into a domain `Observation`.
- **Outbound:** `ObservationResponse.from_domain()` serializes persisted observations for clients.
- **Measurement type:** the value object is flattened to a string field (`measurement_type`) at the API edge.

Validation failures return `422 Unprocessable Entity`. Duplicate identifiers return `409 Conflict`. Missing observations return `404 Not Found`.

### Automatic reasoning lifecycle

When an observation is accepted through `POST /observations`, the platform executes a **synchronous reasoning cycle** inside the same request lifecycle. Clients do not need to know reasoning is occurring — the API contract is unchanged.

```
POST /observations
    │
    ▼
ObservationService.create()
    │  persist observation
    ▼
Load asset observations (list_by_asset)
    │
    ▼
ReasoningSession.run()  (when sufficient evidence exists)
    │  produce OperationalSituation, StructuredAssessment,
    │  PlanningContext, DecisionContext, DecisionPlan, ReasoningTrace
    ▼
Persist reasoning artifacts
    │
    ▼
Return 201 with observation payload
```

Reasoning runs only when an asset has at least two observations of the primary measurement type (the earliest observation's measurement type). A single observation is persisted without triggering reasoning — trend and variation detection require a minimum evidence window.

Orchestration lives in `ObservationService`. The API router remains thin: it validates input, delegates to the application service, and maps HTTP status codes. No background workers, message queues, or asynchronous orchestration are introduced in this slice.

The platform wires `ReasoningSession` with the fuel cell operational profile (`FuelCellOperationalProfile`) and a default operational goal. The reasoning engine itself remains independent of SQLAlchemy, FastAPI, and database concerns.

### Reasoning persistence

Reasoning artifacts are persisted through the same repository pattern as observations. Domain and application models are reused without duplication; infrastructure mappers translate between ORM rows and immutable models.

| Artifact | Layer | Table | Repository |
|----------|-------|-------|------------|
| `ReasoningRun` | application | `reasoning_runs` | `SqlAlchemyReasoningRunRepository` |
| `OperationalSituation` | domain | `operational_situations` | `SqlAlchemySituationRepository` |
| `DecisionContext` | domain | `decision_contexts` | `SqlAlchemyDecisionContextRepository` |
| `DecisionPlan` | domain | `decision_plans` | `SqlAlchemyDecisionPlanRepository` |
| `ReasoningRunIndex` | application | `reasoning_run_indexes` | `SqlAlchemyReasoningRunIndexRepository` |
| `StructuredAssessment` | application | `structured_assessments` | `SqlAlchemyStructuredAssessmentRepository` |
| `ReasoningTrace` | application | `reasoning_traces` | `SqlAlchemyReasoningTraceRepository` |

`StructuredAssessment` and `ReasoningTrace` are keyed by `run_id` (foreign key to `reasoning_runs`). `ReasoningRunIndex` links each run to the observation, situation, context, plan, action, and outcome identifiers produced during the session.

`ReasoningSession` persists domain artifacts (situation, context, plan, run, index) when repository implementations are injected. `ObservationService` persists application-layer artifacts (`StructuredAssessment`, `ReasoningTrace`) after the session completes. Observations are persisted by the service before reasoning begins; the session does not re-save observations that are already stored.

The Alembic migration `c4f1a8d29e10` creates all reasoning artifact tables. Observations remain in the `observations` table from the initial migration.

### Orchestration responsibilities

| Layer | Responsibility |
|-------|----------------|
| **API router** | Validate HTTP payloads, call `ObservationService`, map errors to status codes |
| **ObservationService** | Persist observation, gather asset evidence, invoke `ReasoningSession`, persist `StructuredAssessment` and `ReasoningTrace` |
| **ReasoningSession** | Execute deterministic reasoning pipeline; persist domain artifacts when repositories are wired |
| **Repositories** | Map domain/application models ↔ ORM; append-only inserts |
| **Reasoning engine** | No knowledge of HTTP, SQLAlchemy, or FastAPI |

Dependency injection constructs a request-scoped `ReasoningSession` with all SQLAlchemy repository implementations, then injects it into `ObservationService` alongside the structured assessment and reasoning trace repositories.

### Configuration

Database connectivity is configured through Pydantic Settings. Set `DATABASE_URL` to a PostgreSQL connection string in production (e.g. `postgresql+psycopg://user:pass@host/db`). When unset, the API starts without a database connection; persistence features activate once `DATABASE_URL` is provided.

---

## Deployment Vision

### Initial deployment: Docker Compose

The first production-shaped deployment runs entirely through Docker Compose:

| Service | Technology | Purpose |
|---------|------------|---------|
| **Platform API** | FastAPI (Python) | HTTP API, reasoning orchestration |
| **Database** | PostgreSQL | Durable persistence |
| **Message broker** | MQTT (e.g., Mosquitto) | Industrial telemetry transport |
| **Dashboard** | React (TypeScript) | Operator interface |
| **Simulator** | Python | Fuel cell telemetry generation for development |

```
┌─────────────────────────────────────────────────────────┐
│                  Docker Compose Stack                    │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ FastAPI  │  │PostgreSQL│  │  MQTT    │  │ React  │ │
│  │ Platform │──│          │  │  Broker  │  │Dashboard│ │
│  └────┬─────┘  └──────────┘  └────┬─────┘  └───┬────┘ │
│       │                           │             │      │
│  ┌────┴─────┐                ┌────┴─────┐       │      │
│  │ Reasoning│                │Ingestion │       │      │
│  │ Engine   │                │ Service  │       │      │
│  └──────────┘                └──────────┘       │      │
│                                                 │      │
│  ┌──────────────┐                               │      │
│  │ Fuel Cell    │── MQTT publish ──────────────┘      │
│  │ Simulator    │                                      │
│  └──────────────┘                                      │
└─────────────────────────────────────────────────────────┘
```

Docker Compose provides:

- **Reproducible development environments** — every developer runs the same stack
- **Integration testing** — end-to-end validation across all services
- **Initial deployment target** — suitable for edge deployments and pilot installations

### Scaling toward Kubernetes

The Docker Compose stack maps naturally to a Kubernetes deployment without changing platform responsibilities:

| Compose service | Kubernetes equivalent (future) |
|-----------------|-------------------------------|
| FastAPI Platform | Deployment + Service |
| PostgreSQL | StatefulSet or managed database |
| MQTT Broker | Deployment or managed messaging |
| React Dashboard | Deployment + Ingress |
| Ingestion Service | Deployment (horizontally scalable) |
| Fuel Cell Simulator | Deployment (dev/staging only) |

Subsystem boundaries, API contracts, and data flows remain identical. Only orchestration, scaling, and infrastructure management change. Kubernetes implementation details are out of scope for this document.

---

## Technology Roadmap

The following stack is the planned production technology foundation. Items marked *future* are intended but not part of the initial platform delivery.

### Backend

| Technology | Purpose |
|------------|---------|
| Python | Primary backend language |
| FastAPI | HTTP API framework |
| SQLAlchemy | ORM and database access |
| Alembic | Database migrations |
| PostgreSQL | Primary data store |

### Messaging

| Technology | Purpose |
|------------|---------|
| MQTT | Initial industrial telemetry transport |
| Kafka | *Future* — high-throughput event streaming and replay |

### Industrial

| Technology | Purpose |
|------------|---------|
| OPC UA | Industrial protocol adapter for equipment integration |

### Frontend

| Technology | Purpose |
|------------|---------|
| React | UI framework |
| TypeScript | Type-safe frontend development |
| Tailwind CSS | Utility-first styling |

### Infrastructure

| Technology | Purpose |
|------------|---------|
| Docker | Container packaging |
| Docker Compose | Local development and initial deployment |
| Kubernetes | *Future* — production orchestration and scaling |

### Quality

| Technology | Purpose |
|------------|---------|
| pytest | Test framework |
| Ruff | Linting and formatting |
| mypy | Static type checking |
| GitHub Actions | Continuous integration |

### Observability (future)

| Technology | Purpose |
|------------|---------|
| Prometheus | Metrics collection |
| Grafana | Metrics visualization and dashboards |
| OpenTelemetry | Distributed tracing and instrumentation |

---

## Guiding Principles

These principles govern platform implementation decisions:

1. **Reasoning remains deterministic.** The reasoning engine produces the same output for the same input. No machine learning, no probabilistic black boxes in the core reasoning path. Explainability is non-negotiable.

2. **Platform components remain loosely coupled.** Subsystems communicate through APIs and repository interfaces. No shared mutable state across service boundaries.

3. **APIs are the primary integration boundary.** Every consumer — ingestion, dashboard, external systems — integrates through documented HTTP contracts.

4. **Infrastructure should be replaceable.** Databases, message brokers, and deployment targets can change without rewriting domain or application logic.

5. **Domain knowledge remains profile-driven.** New industrial domains are added through operational profiles, not by modifying the reasoning engine or platform core.

6. **Build production software rather than demonstrations.** Examples and simulators support development; the platform itself is designed for continuous operation in industrial environments.

7. **Favor maintainability over unnecessary complexity.** Choose straightforward patterns that a small team can operate. Add complexity only when a concrete requirement demands it.

---

## Out of Scope

This document intentionally does **not** define:

| Topic | Will be defined in |
|-------|-------------------|
| REST endpoint specifications | API implementation PR |
| Database schema | Persistence implementation PR |
| MQTT topic hierarchy | Ingestion implementation PR |
| Kafka topology | Kafka integration PR |
| Authentication | Security implementation PR |
| Authorization | Security implementation PR |
| Deployment manifests | Deployment implementation PR |
| Infrastructure-as-Code | Infrastructure implementation PR |

Each topic will receive its own implementation PR with detailed specifications. This document establishes the architectural frame; implementation PRs fill in the details.

---

## Phase 2 Roadmap

High-level implementation sequence for the production platform:

| Step | Deliverable | Description |
|------|-------------|-------------|
| 1 | **FastAPI platform foundation** | HTTP API skeleton, project structure, health endpoints, service wiring |
| 2 | **Docker Compose development environment** | Multi-service local stack with reproducible startup |
| 3 | **PostgreSQL persistence** | Database foundation (engine, sessions, migrations, repository abstractions); entity repository implementations follow in subsequent PRs |
| 4 | **Reasoning API** | Endpoints that trigger reasoning and return assessments and plans |
| 5 | **Fuel cell simulator** | Realistic telemetry generator for development and demonstration |
| 6 | **MQTT ingestion** | Subscriber service that receives telemetry and forwards to API |
| 7 | **React dashboard** | Operator interface for monitoring assessments and reasoning history |
| 8 | **Historical replay** | Reconstruct and replay reasoning from persisted artifacts |
| 9 | **Kafka integration** | High-throughput event streaming as an alternative ingestion path |
| 10 | **Production deployment improvements** | Hardening, observability, scaling preparation |

This roadmap is intentionally high level. Each step may span multiple PRs. Sequencing reflects dependency order — persistence before reasoning API, ingestion before dashboard — but parallel work is possible where boundaries are clean.

---

## Related Documentation

| Document | Scope |
|----------|-------|
| [Architecture](../architecture.md) | Codebase organization and reasoning layer design |
| [Reasoning Pipeline](../reasoning-pipeline.md) | Stage-by-stage reasoning flow |
| [Research](../research/) | Theoretical foundations for operational reasoning |
| [RFCs](../rfcs/) | Formal design proposals for reasoning features |
| [Fuel Cell Profile](../profiles/fuel_cell_profile.md) | Domain profile for PEM fuel cell demonstration |
