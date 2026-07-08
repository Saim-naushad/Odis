# ODIS Platform Backend

HTTP API service for the ODIS industrial operational intelligence platform.

This package is the canonical entry point into the production platform. It exposes REST endpoints, application lifecycle management, and configuration wiring that future platform features (persistence, ingestion, reasoning orchestration, dashboards) will build upon.

The reasoning engine remains in `src/` as a separate subsystem. This backend does not embed reasoning logic directly in its foundation phase.

## Structure

```
backend/
  app/
    api/                 # HTTP layer (routers, schemas, dependencies)
    infrastructure/      # Configuration, database, repository adapters
      database/          # SQLAlchemy engine, session factory, declarative base
      repositories/      # Repository abstractions for future implementations
    main.py              # FastAPI application factory
```

## Running locally

Install project dependencies:

```bash
pip install -e ".[dev]"
```

Start the API server:

```bash
uvicorn backend.app.main:app --reload
```

OpenAPI documentation is available at `/docs`.

## Configuration

Settings are loaded from environment variables (and an optional `.env` file) via Pydantic Settings. Core fields:

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `ODIS Platform` | Service title shown in OpenAPI |
| `APP_VERSION` | `0.1.0` | API version |
| `ENVIRONMENT` | `development` | Deployment environment label |
| `DATABASE_URL` | *(unset)* | PostgreSQL or SQLite connection string; enables persistence when set |

Reserved for future use: `MQTT_BROKER_URL`, `KAFKA_BOOTSTRAP_SERVERS`.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Platform metadata |
| `GET` | `/health` | Liveness check |
