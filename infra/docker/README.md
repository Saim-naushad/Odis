# Docker support files

Configuration and image definitions for the ODIS runtime.

**Start the stack from the repository root:**

```bash
docker compose up --build -d
```

See [docs/platform/docker-runtime.md](../../docs/platform/docker-runtime.md) for the full topology, networking, volumes, and health dependencies.

## Layout

| Path | Purpose |
|------|---------|
| `api/` | FastAPI image and entrypoint (migrations + uvicorn) |
| `worker/` | Reasoning worker image |
| `nginx/` | Frontend reverse proxy (`/api` → API service) |
| `prometheus/` | Scrape configuration |
| `grafana/` | Datasource and dashboard provisioning |

The canonical Compose file is `docker-compose.yml` at the repository root.
