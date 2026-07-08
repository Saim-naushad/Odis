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

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
