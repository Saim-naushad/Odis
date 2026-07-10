# Historical Telemetry APIs

This document describes how ODIS retrieves raw sensor telemetry for operator-facing history views. It builds on the [TimescaleDB Foundation](timescaledb-foundation.md) and complements monitoring endpoints that expose **reasoning history**, not time-series measurements.

For platform context, see [Platform Architecture](platform-architecture.md).

---

## Why Historical Telemetry Is Separate from Reasoning

ODIS has two distinct monitoring concerns:

| Concern | Source | Example endpoints |
|---------|--------|-------------------|
| **Reasoning history** | `reasoning_runs`, `decision_plans`, traces | `/monitoring/assets/{id}/history`, `/monitoring/runs/{id}` |
| **Telemetry history** | `observations` hypertable | `/monitoring/assets/{id}/telemetry` |

Reasoning endpoints answer *what the platform concluded* at a point in time. Telemetry endpoints answer *what was measured* over time. Keeping them separate:

- Preserves stable reasoning APIs as telemetry volume grows
- Allows time-range queries without loading full reasoning artifacts
- Prepares dashboards to consume continuous aggregates later without coupling to reasoning runs

The reasoning worker still loads observations for assessment; telemetry APIs are read-only projections for operators and future charting.

---

## TelemetrySeries Domain Model

Historical telemetry is exposed through an immutable domain projection — not ORM models or raw `Observation` entities.

```python
@dataclass(frozen=True)
class TelemetrySample:
    timestamp: datetime
    value: float

@dataclass(frozen=True)
class TelemetrySeries:
    asset_id: str
    measurement_type: str
    unit: str
    samples: tuple[TelemetrySample, ...]  # oldest → newest
```

| Field | Role |
|-------|------|
| `asset_id` | Asset scope for the series |
| `measurement_type` | Metric label (for example `stack_temperature`) |
| `unit` | Display unit for all samples in the series |
| `samples` | Ordered timestamp/value pairs |

`TelemetryHistoryService` is the **single place** historical telemetry is assembled. API handlers map `TelemetrySeries` to stable JSON via `TelemetrySeriesResponse`; they never return SQLAlchemy models.

---

## Query Flow

```mermaid
sequenceDiagram
    participant UI as Monitoring Dashboard
    participant API as FastAPI /monitoring
    participant SVC as TelemetryHistoryService
    participant REPO as ObservationRepository
    participant DB as observations hypertable

    UI->>API: GET /assets/{id}/telemetry?start=&end=
    API->>SVC: get_history(asset_id, filters)
    SVC->>REPO: list_by_asset_in_time_range(...)
    REPO->>DB: SQL time-range query (standard SQLAlchemy)
    DB-->>REPO: Observation rows
    REPO-->>SVC: domain Observation list
    SVC-->>SVC: group by measurement_type → TelemetrySeries
    SVC-->>API: list[TelemetrySeries]
    API-->>UI: list[TelemetrySeriesResponse]
```

Pipeline summary:

1. **API** validates asset existence, time window, and `limit` (1–10,000).
2. **TelemetryHistoryService** queries observations and groups them into `TelemetrySeries`.
3. **ObservationRepository** issues efficient time-range filters using existing hypertable indexes — no Timescale-specific SQL in the application layer.
4. **Response** returns chronologically ordered samples per measurement type.

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/monitoring/assets/{asset_id}/telemetry` | Historical samples in an optional time window |
| `GET` | `/monitoring/assets/{asset_id}/telemetry/latest` | Newest samples per measurement type |

### Query parameters

| Parameter | Endpoints | Description |
|-----------|-----------|-------------|
| `start` | history | Inclusive window start (ISO 8601) |
| `end` | history | Inclusive window end (ISO 8601) |
| `measurement_type` | both | Optional metric filter |
| `limit` | both | Max raw observations (default 1000 history / 1 latest) |

Responses return `list[TelemetrySeriesResponse]` — stable, operator-friendly JSON grouped by measurement type.

---

## Industrial API Patterns Adopted

Research across TimescaleDB, Grafana, Azure IoT Hub, and AWS IoT SiteWise informed the design. ODIS adopted only patterns that fit a reasoning-centric platform:

| Pattern | Source inspiration | ODIS adoption |
|---------|-------------------|---------------|
| Asset-scoped history | SiteWise `GetAssetPropertyValueHistory` | `/monitoring/assets/{id}/telemetry` |
| Time-range filters | Grafana / Timescale `time_bucket` queries | `start` / `end` query params |
| Metric filtering | Azure IoT message queries | `measurement_type` param |
| Latest value reads | Grafana instant queries | `/telemetry/latest` |
| Series grouping | Grafana time-series panels | `TelemetrySeries` per metric |

Not adopted: Flux/InfluxQL, SiteWise asset model imports, Grafana dashboard query DSL, or forecasting endpoints.

---

## Repository Extension

`ObservationRepository` gained one method:

```python
def list_by_asset_in_time_range(
    self,
    asset_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    measurement_type: str | None = None,
    limit: int | None = None,
    newest_first: bool = False,
) -> list[Observation]:
```

SQLAlchemy uses standard `WHERE` + `ORDER BY` + `LIMIT` against indexes defined in the TimescaleDB foundation migration. The in-memory implementation mirrors the contract for tests.

---

## Frontend Integration

The monitoring dashboard includes a **Telemetry History** panel that lists recent measurements per metric (no charts yet). It calls `GET /monitoring/assets/{id}/telemetry` with a configurable limit.

Charts can build on continuous aggregate endpoints for downsampled rollups; see [Continuous Aggregates](continuous-aggregates.md).

---

## Continuous Aggregates

Downsampled telemetry is available via `ContinuousAggregateService` and `GET /monitoring/assets/{id}/telemetry/aggregate`. See [Continuous Aggregates](continuous-aggregates.md) for view definitions, refresh policies, and the relationship to raw history.

The monitoring dashboard includes an **Aggregate Summary** panel (hourly/daily toggles, no charts).

---

## Future: ONNX

| Capability | Relationship to telemetry APIs |
|------------|-------------------------------|
| **ONNX inference** | Forecasting models will consume aggregated or windowed telemetry; inference stays out of historical retrieval APIs |

Raw `TelemetrySeries` responses stay stable. ONNX adds a parallel read path without changing the domain contract.

---

## Architecture

```mermaid
flowchart TB
    subgraph presentation["Presentation"]
        DASH["Monitoring Dashboard"]
        PANEL["Telemetry History Panel"]
    end

    subgraph api["API Layer"]
        ROUTER["/monitoring/assets/{id}/telemetry"]
        SCHEMA["TelemetrySeriesResponse"]
    end

    subgraph application["Application"]
        SVC["TelemetryHistoryService"]
        SERIES["TelemetrySeries"]
    end

    subgraph domain["Domain / Infrastructure"]
        REPO["ObservationRepository"]
        OBS[("observations hypertable")]
    end

    subgraph reasoning["Reasoning (separate path)"]
        MON["MonitoringService"]
        RUNS[("reasoning_runs")]
    end

    DASH --> PANEL
    PANEL --> ROUTER
    ROUTER --> SVC
    SVC --> SERIES
    SVC --> REPO
    REPO --> OBS
    MON --> RUNS
    MON -.->|"existence check only"| REPO
```

---

## Related Documentation

| Document | Topic |
|----------|-------|
| [TimescaleDB Foundation](timescaledb-foundation.md) | Hypertable schema, indexes, analytics roadmap |
| [Platform Architecture](platform-architecture.md) | Overall platform design |
