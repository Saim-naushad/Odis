## Frontend – ODIS Monitoring Console

React 19 + TypeScript + Vite operator console for the ODIS platform. It is a
single page (no router) that connects to the FastAPI backend for fleet
health, telemetry, recommendations, and the investigation timeline.

For the composed layout and overall dashboard behavior, see
`MonitoringDashboard.tsx` and `components/monitoring/*`. For platform-level
architecture, see [Platform Architecture](../docs/platform/platform-architecture.md).

### Setup

- **Node.js**: use a recent LTS version.
- From the repository root:

```bash
cd frontend
npm install
```

### Development

Start the FastAPI backend (from the repo root):

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Then run the frontend dev server:

```bash
cd frontend
npm run dev
```

By default Vite runs on `http://localhost:5173` and proxies `/api/*` to
`http://localhost:8000`, stripping the `/api` prefix.

### State and real-time updates

State is entirely React Query. `GET /monitoring/events` (Server-Sent Events)
pushes targeted cache invalidation as reasoning results, telemetry, and
investigation transitions change; a 60-second poll is a fallback used only
when SSE is disconnected.

Key backend endpoints used:

- `GET /monitoring/assets` – list known assets.
- `GET /monitoring/assets/{asset_id}/digital-twin` – composed read model (state, recommendation, telemetry, forecast, investigation status).
- `GET /monitoring/assets/{asset_id}/telemetry` and `/telemetry/aggregate` – raw and rolled-up telemetry history.
- `GET /monitoring/assets/{asset_id}/timeline` – reasoning and investigation events.
- `POST /monitoring/assets/{asset_id}/investigation` – operator investigation transitions (acknowledge / investigate / resolve).
- `GET /monitoring/events` – SSE stream for real-time cache invalidation.

### Architecture

- **`src/api`** – thin API client layer wrapping `fetch`, including the SSE client.
- **`src/types`** – TypeScript interfaces mirroring the FastAPI response schemas.
- **`src/hooks`** – `useMonitoringDashboard`, `useMonitoringSse`, `useInvestigationTransition`, `useTelemetryVisualization`.
- **`src/monitoring`** – SSE event dispatcher and event-type definitions.
- **`src/components/monitoring`** – presentational components composing the dashboard (fleet strip, telemetry, investigation timeline, recommendations).
- **`src/pages`** – `MonitoringDashboard`, the single page that composes the console.

Operators can transition an asset's investigation status (acknowledge,
investigate, resolve) from the dashboard; all other views are read-only.
Tailwind CSS is used for layout and an industrial, console-style aesthetic.
