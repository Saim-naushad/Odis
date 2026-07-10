# Docker Runtime

This document describes the production-oriented Docker runtime for ODIS. The Compose stack defines the service topology that Kubernetes and other orchestrators should inherit.

For platform context, see [Platform Architecture](platform-architecture.md).

---

## Service topology

| Service | Image / build | Role | Public port |
|---------|---------------|------|-------------|
| **frontend** | `frontend/Dockerfile` (nginx + React build) | Operator monitoring console; proxies `/api` to the API | `8080` → `80` |
| **api** | `infra/docker/api/Dockerfile` | FastAPI platform API, metrics, health probes | `8000` |
| **worker** | `infra/docker/worker/Dockerfile` | Background reasoning job processor | internal |
| **postgres** | `timescale/timescaledb:2.17.2-pg16` | Durable platform state and telemetry hypertables | internal |
| **redis** | `redis:7-alpine` | Digital twin cache | internal |
| **kafka** | `apache/kafka:3.9.0` (KRaft) | Event streaming backbone | internal |
| **prometheus** | `prom/prometheus` | Metrics collection | internal |
| **grafana** | `grafana/grafana` | Dashboards and visualization | internal |

Kafka runs in **KRaft mode** (combined broker + controller). No Zookeeper service is required.

---

## Architecture

```mermaid
flowchart TB
    subgraph public["Public endpoints"]
        Browser["Browser / operator"]
    end

    subgraph odis_internal["odis-internal network"]
        FE["frontend :80"]
        API["api :8000"]
        WRK["worker"]
        PG[("postgres")]
        RD["redis"]
        KF["kafka (KRaft)"]
        PR["prometheus"]
        GF["grafana"]
    end

    Browser -->|"http://localhost:8080"| FE
    Browser -->|"http://localhost:8000 (optional direct API)"| API
    FE -->|"/api/* proxy"| API
    API --> PG
    API --> RD
    API --> KF
    WRK --> PG
    WRK --> KF
    PR -->|"/metrics scrape"| API
    GF -->|"Prometheus datasource"| PR
```

ASCII equivalent:

```
                    ┌─────────────┐
  Browser ─────────▶│  frontend   │ :8080 (public)
                    │   (nginx)   │
                    └──────┬──────┘
                           │ /api/*
                           ▼
                    ┌─────────────┐
  Browser ─────────▶│     api     │ :8000 (public)
                    │  (FastAPI)  │
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
      ┌─────────┐    ┌─────────┐    ┌─────────┐
      │ postgres│    │  redis  │    │  kafka  │  (internal)
      └─────────┘    └─────────┘    └─────────┘
                           ▲
                           │
                    ┌──────┴──────┐
                    │   worker    │  (internal)
                    └─────────────┘

      prometheus ──scrape──▶ api /metrics   (internal)
      grafana ──query──▶ prometheus          (internal)
```

---

## Networking

All services attach to a single bridge network: `odis-internal`.

**Exposed to the host:**

- `frontend` → `${FRONTEND_PORT:-8080}`
- `api` → `${API_PORT:-8000}`

**Internal only:**

- `postgres`, `redis`, `kafka`, `worker`, `prometheus`, `grafana`

The frontend nginx container proxies browser requests from `/api/*` to the API service, matching the Vite dev proxy behavior.

---

## Persistence

Named Docker volumes:

| Volume | Service | Mount |
|--------|---------|-------|
| `odis-postgres-data` | postgres | `/var/lib/postgresql/data` |
| `odis-kafka-data` | kafka | `/var/lib/kafka/data` |
| `odis-prometheus-data` | prometheus | `/prometheus` |
| `odis-grafana-data` | grafana | `/var/lib/grafana` |

Grafana dashboards and datasources are provisioned from `infra/docker/grafana/` at container start.

---

## Health and startup order

Health probes use the endpoints from PR130:

| Service | Probe | Compose usage |
|---------|-------|---------------|
| **api** | `GET /live` | Compose healthcheck (liveness; avoids worker startup deadlock) |
| **api** | `GET /ready` | Operational readiness (checks postgres, redis, kafka, worker heartbeat) |
| **postgres** | `pg_isready` |
| **redis** | `redis-cli ping` |
| **kafka** | `kafka-topics.sh --list` |
| **worker** | process check (`pgrep`) |
| **frontend** | HTTP `GET /` |
| **prometheus** | `/-/healthy` |
| **grafana** | `/api/health` |

Startup dependencies (no arbitrary `sleep`):

1. `postgres`, `redis`, `kafka` become healthy
2. `api` runs Alembic migrations, starts uvicorn, passes `/live`
3. `worker`, `frontend`, and `prometheus` start after `api` is live
4. `worker` records heartbeats; `/ready` returns 200 once the worker is healthy
5. `grafana` starts after `prometheus` is healthy

---

## Configuration

Runtime configuration is centralized in:

- `.env` — local overrides (not committed)
- `.env.example` — documented defaults

Compose injects shared API/worker environment via the `x-odis-environment` anchor in `docker-compose.yml`.

---

## Startup

From the repository root:

```bash
cp .env.example .env   # optional
docker compose up --build -d
```

Verify:

```bash
docker compose ps
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8080/
```

Open the monitoring console at `http://localhost:8080`.

---

## Local development

### Full stack in Docker

Use Compose when you want the complete platform (database, cache, messaging, observability) without installing dependencies on the host:

```bash
docker compose up --build
```

### Hybrid: infrastructure in Docker, apps on host

Run only infrastructure services (publish host ports for hybrid development):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis kafka prometheus grafana
export DATABASE_URL=postgresql+psycopg://odis:odis@localhost:5432/odis
alembic upgrade head
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
python -m backend.app.worker_main
cd frontend && npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000`.

### Host migrations against Compose Postgres

When Postgres runs in Docker but you execute Alembic on the host:

```bash
export DATABASE_URL=postgresql+psycopg://odis:odis@localhost:5432/odis
alembic upgrade head
```

Expose Postgres temporarily by adding a `ports` mapping only for local debugging if needed.

---

## Production runtime notes

- The Compose file is the reference topology for Kubernetes manifests: one deployment per service, internal ClusterIP for private services, Ingress for `frontend` and `api`.
- API images run `alembic upgrade head` on startup; in Kubernetes, prefer a dedicated migration Job for production rollouts.
- Pin image tags in production (`timescale/timescaledb:2.17.2-pg16`, `prom/prometheus:v3.2.1`, etc.) as shown in `docker-compose.yml`.
- Grafana and Prometheus are internal; route operator traffic through the frontend and API only.

---

## File layout

```
docker-compose.yml              # Canonical runtime definition
.env.example                    # Shared configuration template
infra/docker/
  api/Dockerfile                # API image
  api/entrypoint.sh             # Migrations + uvicorn
  worker/Dockerfile             # Worker image
  nginx/default.conf            # Frontend reverse proxy
  prometheus/prometheus.yml     # Scrape config
  grafana/                      # Provisioning + dashboards
frontend/Dockerfile             # Multi-stage React + nginx build
```

The duplicate `infra/docker/docker-compose.yml` has been removed; use the root `docker-compose.yml` only.
