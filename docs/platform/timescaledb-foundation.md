# TimescaleDB Foundation

This document describes how ODIS introduces TimescaleDB as a PostgreSQL extension for industrial telemetry storage. TimescaleDB extends the existing relational database; it does not replace PostgreSQL or change application connection strings.

For platform context, see [Platform Architecture](platform-architecture.md). For Docker and Kubernetes runtime details, see [Docker Runtime](docker-runtime.md) and [Kubernetes Deployment](kubernetes-deployment.md).

---

## Why TimescaleDB

ODIS ingests continuous operational measurements and persists reasoning artifacts alongside them. Today, all measurements flow through the domain `Observation` entity and the `observations` table. As telemetry volume grows, time-partitioned storage, efficient time-range queries, and future retention/compression policies become important.

TimescaleDB adds hypertables, chunk-based time partitioning, and time-series analytics primitives on top of PostgreSQL. ODIS keeps:

- PostgreSQL wire protocol and SQLAlchemy repositories
- Domain and application identity models unchanged
- Relational tables for reasoning jobs, plans, timeline events, and platform state

TimescaleDB is adopted only where append-heavy telemetry justifies it.

---

## Why TimescaleDB instead of InfluxDB?

InfluxDB is a purpose-built time-series database optimized for high-cardinality metric ingest and downsampling. ODIS chose TimescaleDB for this foundation because the platform's core value is **explainable operational reasoning on relational evidence**, not standalone metrics storage.

| Factor | TimescaleDB on PostgreSQL | InfluxDB |
|--------|---------------------------|----------|
| **Data model** | Telemetry (`observations` hypertable) and reasoning artifacts (`decision_plans`, `reasoning_jobs`, etc.) coexist in one database | Telemetry and relational domain state require a separate store or sync layer |
| **Query surface** | Standard SQL joins across telemetry and reasoning history | Flux/InfluxQL; cross-store joins with reasoning artifacts are awkward |
| **Application transparency** | Existing SQLAlchemy repositories and `DATABASE_URL` unchanged | New client SDK, query language, and operational stack |
| **Transactional consistency** | Observation persist + reasoning job enqueue in one PostgreSQL transaction | Dual-write or eventual consistency between TSDB and relational store |
| **Operational footprint** | One database image replaces `postgres:16`; same backups and tooling | Additional service to deploy, monitor, and secure |

InfluxDB remains a valid choice for pure metrics platforms. ODIS is a reasoning platform that happens to ingest telemetry — keeping telemetry inside PostgreSQL preserves auditability, simplifies deployment, and avoids splitting the evidence chain across databases.

---

## Relational vs Telemetry Data

| Category | Examples | Storage model |
|----------|----------|---------------|
| **Telemetry** | Raw sensor measurements (`observations`) | Hypertable partitioned on `timestamp` |
| **Relational / domain** | `reasoning_jobs`, `decision_plans`, `structured_assessments`, `timeline_events`, `worker_heartbeats` | Standard PostgreSQL tables |
| **Future high-volume telemetry** | Dedicated streams such as voltage, current, power, vibration | Separate hypertables when volume warrants them; domain `Observation` remains the integration contract today |

`timeline_events` is time-ordered but represents operational audit events, not raw sensor telemetry. It stays a regular table.

Monitoring history is assembled from reasoning artifacts (`reasoning_run_indexes`, `reasoning_runs`), not from a separate time-series table.

---

## Initial Hypertable: `observations`

`observations` is the only table converted to a hypertable in this foundation phase.

| Column | Role |
|--------|------|
| `id` | Application-level observation identity (unchanged) |
| `asset_id` | Asset scope for queries and future compression segmentation |
| `timestamp` | Hypertable partition column (`timestamptz`) |
| `measurement_type_name` | Metric label |
| `value`, `unit` | Measurement payload |

Chunk interval starts at **1 day**, a conservative default for current ingest volume. It can be tuned later based on row counts per chunk.

Query-oriented indexes support current repository access patterns:

- `(asset_id, timestamp DESC)` for asset history
- `(asset_id, measurement_type_name, timestamp DESC)` for metric-specific reads and future analytics
- Non-unique index on `id` for `get(id)` lookups

---

## Primary Key Constraint on Hypertables

TimescaleDB still requires that every `PRIMARY KEY` or `UNIQUE` constraint on a hypertable include all partitioning columns. Because `observations` is partitioned on `timestamp`, an `id`-only primary key cannot be preserved at the database level when the table becomes a hypertable.

This is documented in current TimescaleDB guidance:

- [Enforce constraints with unique indexes](https://docs.timescale.com/use-timescale/latest/hypertables/hypertables-and-unique-indexes/)
- [Primary keys, time, and uniqueness](https://www.tigerdata.com/docs/learn/data-model/primary-keys-time-and-uniqueness)

Supported options for append-only telemetry:

| Approach | Database effect | ODIS choice |
|----------|-----------------|-------------|
| Composite `PRIMARY KEY (id, timestamp)` | DB-enforced uniqueness including time | Not used — changes physical identity semantics |
| `id`-only `PRIMARY KEY` | Not supported on hypertables | Not possible |
| **No unique constraint; non-unique index on `id`** | Application enforces duplicate rejection; faster append-only ingest | **Preferred** |

`observations` are immutable and append-only. `SqlAlchemyObservationRepository.save()` already rejects duplicate IDs before insert. The migration therefore:

1. Drops the `id`-only primary key constraint
2. Converts `observations` to a hypertable on `timestamp`
3. Adds a non-unique index on `id` for efficient lookups

The domain `Observation.id` and repository contracts remain unchanged. Only the database constraint model changes to satisfy TimescaleDB hypertable rules.

---

## Future Telemetry Evolution

Today's domain model exposes a single `Observation` abstraction regardless of measurement type. That contract stays stable for ingestion, reasoning, and APIs.

As industrial telemetry volume grows, ODIS may introduce dedicated hypertables for high-frequency streams without changing today's domain model immediately. Examples:

| Future table | Example signals | When |
|--------------|-----------------|------|
| `voltage_readings` | Stack/cell voltage | Sustained high-frequency ingest |
| `current_readings` | Load current | Same |
| `power_readings` | Derived or measured power | Same |
| `vibration_readings` | Mechanical vibration spectra | Same |

A likely evolution path:

1. **Today:** all measurements persist to `observations` (hypertable).
2. **Later:** hot high-volume streams write to dedicated hypertables optimized for ingest and rollups.
3. **Integration:** ingestion adapters or infrastructure repositories map external telemetry into domain `Observation` values for reasoning; reasoning continues to consume domain objects, not Timescale-specific SQL.

Dedicated telemetry tables are an infrastructure scaling step, not a domain redesign.

---

## Future Analytics Roadmap (Not Enabled Yet)

The schema and indexes are prepared for later capabilities. None are enabled in the foundation phase.

| Capability | Fit in ODIS | Planned trigger |
|------------|-------------|-----------------|
| **Continuous aggregates** | Pre-computed `time_bucket()` rollups for monitoring dashboards (hourly/daily asset metrics) | Enabled — see [Continuous Aggregates](continuous-aggregates.md) |
| **Compression** | Segment by `asset_id`, order by `timestamp DESC` on historical chunks | Storage growth after warm data ages out |
| **Retention policies** | Drop raw telemetry beyond operational window; keep reasoning artifacts | Agreed data lifecycle / compliance window |

Example continuous aggregate (see [Continuous Aggregates](continuous-aggregates.md) for full definitions and refresh policies):

```sql
CREATE MATERIALIZED VIEW observations_hourly
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 hour', timestamp) AS bucket,
  asset_id,
  measurement_type_name,
  avg(value) AS avg_value,
  min(value) AS min_value,
  max(value) AS max_value,
  count(*) AS sample_count
FROM observations
GROUP BY bucket, asset_id, measurement_type_name;
```

Compression and retention would attach to `observations` or future dedicated telemetry hypertables once retention windows are defined.

---

## Architecture

Today's platform runs an asynchronous reasoning pipeline. Observations are persisted immediately; reasoning executes in a background worker. TimescaleDB partitions only the telemetry plane — the application layer sees the same repository contracts throughout.

```mermaid
flowchart TB
    subgraph ingest["Ingestion"]
        SIM["Fuel cell simulator / MQTT / OPC UA"]
    end

    subgraph api_proc["API process"]
        API["FastAPI API"]
        OBS_SVC["ObservationService"]
    end

    subgraph worker_proc["Worker process"]
        WRK["Reasoning worker"]
        ENGINE["Reasoning engine"]
    end

    subgraph db["PostgreSQL + TimescaleDB"]
        subgraph telemetry["Telemetry plane"]
            OBS[("observations hypertable")]
        end
        subgraph relational["Relational plane"]
            RJ["reasoning_jobs"]
            RUNS["reasoning_runs"]
            PLANS["decision_plans"]
            ASSESS["structured_assessments"]
            TL["timeline_events"]
        end
    end

    SIM -->|"POST /observations"| API
    API --> OBS_SVC
    OBS_SVC -->|"save"| OBS
    OBS_SVC -->|"enqueue"| RJ
    WRK -->|"claim pending job"| RJ
    WRK -->|"load asset observations"| OBS
    WRK --> ENGINE
    ENGINE -->|"persist artifacts"| RUNS
    ENGINE --> PLANS
    ENGINE --> ASSESS
    ENGINE --> TL
```

Pipeline summary:

1. **Observation** — API persists the measurement to `observations` (hypertable).
2. **Reasoning job** — `ObservationService` enqueues a `reasoning_jobs` row for the asset.
3. **Worker** — background process claims the oldest pending job.
4. **Reasoning engine** — deterministic assessment and planning over stored observations.
5. **Decision artifacts** — situations, contexts, plans, assessments, and traces persist to relational tables.

Repository interfaces, `Observation.id`, and service logic are unchanged. TimescaleDB affects only infrastructure-level storage and indexing.

---

## Runtime

Docker Compose and Kubernetes continue to expose the database service as `postgres` on port `5432`. The container image is `timescale/timescaledb:2.17.2-pg16`. Connection strings remain standard PostgreSQL URLs, for example:

`postgresql+psycopg://odis:odis@postgres:5432/odis`

Alembic migrations enable the `timescaledb` extension and convert `observations` safely on existing databases using `migrate_data => TRUE` and idempotent `if_not_exists` guards.

---

## Related Documentation

| Document | Topic |
|----------|-------|
| [Platform Architecture](platform-architecture.md) | Overall platform design and persistence layout |
| [Continuous Aggregates](continuous-aggregates.md) | Rollup views, refresh policies, and aggregate APIs |
| [Docker Runtime](docker-runtime.md) | Compose service topology |
| [Kubernetes Deployment](kubernetes-deployment.md) | Cluster manifests and operations |
