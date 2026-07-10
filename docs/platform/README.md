# Platform Documentation

This section describes how ODIS is deployed, structured, and operated as an industrial software platform.

It complements the [reasoning architecture](../architecture.md) and [research](../research/) documentation. Those documents explain *how operational reasoning works*; platform documentation explains *how ODIS runs in production* — ingestion, APIs, persistence, dashboards, and deployment.

Platform documents are living references that evolve alongside implementation. They are not RFCs.

| Document | Description |
|----------|-------------|
| [Platform Architecture](platform-architecture.md) | High-level platform design and component roles |
| [TimescaleDB Foundation](timescaledb-foundation.md) | Telemetry hypertables, relational vs time-series data, and analytics roadmap |
| [Docker Runtime](docker-runtime.md) | Compose topology, networking, health, and startup |
| [Kubernetes Deployment](kubernetes-deployment.md) | K8s manifests, networking, scaling, and operations |
| [CI/CD and Container Registry](ci-cd.md) | GitHub Actions validation, GHCR publishing, and image versioning |
