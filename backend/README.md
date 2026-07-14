# ODIS Platform Backend

FastAPI service and background worker that host the ODIS reasoning engine as an
industrial operational intelligence platform.

`backend/app/application/*` orchestrates and persists the reasoning engine in
`src/` — it does not duplicate reasoning logic. For full platform design (Unit
of Work, Outbox, event bus, digital twin composition), see
[Platform Architecture](../docs/platform/platform-architecture.md). For the
end-to-end demo path, see [Demo Environment](../docs/platform/demo-environment.md).

## Structure

```
backend/
  app/
    api/             # FastAPI routers, schemas, dependencies, middleware
    application/     # Use cases orchestrating src/application and src/domain
    domain/          # Platform-only domain objects (e.g. Recommendation, Investigation)
    infrastructure/  # SQLAlchemy repositories, Redis cache, Kafka outbox, tracing, config
    worker_main.py   # Background worker entry point
    main.py          # FastAPI application factory
  mqtt_bridge/       # Mosquitto -> POST /observations bridge
  simulator/         # Plant Alpha, the physics-based PEM fuel-cell simulator
```

## Running locally

See the [README quick start](../README.md#quick-start) for full platform
(Docker Compose) and hybrid (infra in Docker, apps on host) setups. To run the
API alone against an already-running database:

```bash
pip install -e ".[dev]"
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Run the background worker (required for reasoning to execute) in a separate
process:

```bash
python -m backend.app.worker_main
```

OpenAPI documentation is available at `/docs`.

## Configuration

Settings load from environment variables and an optional `.env` file via
Pydantic Settings — see `.env.example` for the full list, including database,
Redis, Kafka, and MQTT connection settings.

## API surface

| Area | Path prefix | Notes |
|------|-------------|-------|
| Platform metadata | `GET /`, `/health`, `/health/live`, `/health/ready` | Liveness, readiness, and version info |
| Observation ingestion | `POST /observations` | Enqueues a reasoning job on receipt |
| Monitoring | `GET /monitoring/assets`, `/assets/{id}/latest`, `/assets/{id}/history` | Reasoning results and history |
| Digital twin | `GET /monitoring/assets/{id}/digital-twin` | Composed read model: state, recommendation, telemetry, forecast, investigation |
| Telemetry | `GET /monitoring/assets/{id}/telemetry`, `/telemetry/aggregate`, `/telemetry/forecast` | Raw history, continuous aggregates, ONNX forecasts |
| Investigation | `POST /monitoring/assets/{id}/investigation` | Operator lifecycle transitions (acknowledged/investigating/resolved) |
| Live updates | `GET /monitoring/events` | Server-Sent Events stream consumed by the dashboard |
| Metrics | `GET /metrics` | Prometheus scrape endpoint |

Full request/response schemas are in `/docs` (Swagger UI) when the API is running.
