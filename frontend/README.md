## Frontend – ODIS Monitoring Console

This package contains the first React + TypeScript monitoring dashboard for ODIS.
It is a read-only operational console that connects to the existing FastAPI backend.

### Setup

- **Node.js**: use a recent LTS version.
- From the repository root:

```bash
cd frontend
npm install
```

### Development

Start the FastAPI backend (from the repo root, command may vary):

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Then run the frontend dev server:

```bash
cd frontend
npm run dev
```

By default Vite runs on `http://localhost:5173`.

### Backend connection

The frontend talks to the existing Monitoring API via a dev-time proxy:

- All HTTP calls are made against the `/api` prefix from the browser.
- `vite.config.ts` configures a proxy that forwards `/api/*` to the FastAPI app on `http://localhost:8000` and strips the `/api` prefix.

Key backend endpoints used:

- `GET /health` – platform liveness.
- `GET /` – platform metadata.
- `GET /monitoring/assets` – list known assets.
- `GET /monitoring/assets/{asset_id}/latest` – latest reasoning result for an asset.
- `GET /monitoring/assets/{asset_id}/history` – reasoning history for an asset.
- `GET /monitoring/runs/{run_id}` – full reasoning run details, including reasoning trace.

### Architecture

- **`src/api`** – thin API client layer wrapping `fetch` and typed per-endpoint functions.
- **`src/types`** – TypeScript interfaces mirroring the FastAPI response schemas.
- **`src/hooks`** – `useMonitoringDashboard` orchestrates polling and state for the dashboard.
- **`src/components`** – small, presentational components for header, asset list, details, reasoning trace, and run history.
- **`src/pages`** – `MonitoringDashboard` page that composes the layout into a single operational console.

No authentication or mutation is implemented; all views are read-only. Tailwind CSS is used for layout and an industrial, console-style aesthetic.
