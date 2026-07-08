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

  Equipment ──▶ Ingestion ──▶ API ──▶ DB     DB ──▶ Reasoning ──▶ Assessment ──▶ DB
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
| 3 | **PostgreSQL persistence** | Schema, migrations, repository implementations for domain entities |
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
