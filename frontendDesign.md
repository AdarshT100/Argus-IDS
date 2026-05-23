# Argus-IDS Frontend Design

## 1. Overview

The recommended frontend direction for Argus-IDS is a Vite + React + TypeScript dashboard that talks to the existing FastAPI backend over HTTP/JSON. 

## 2. Recommended Frontend Stack

- **Vite**: lightweight development server and build tool for a React single-page app.
- **React**: component model for dashboard pages, forms, tables, charts, and reusable UI.
- **TypeScript**: typed API contracts and safer component data handling.
- **TanStack Query**: server-state management for backend calls, loading states, errors, caching, and refetching.
- **Recharts**: charting library for alert, simulation, threshold, and SHAP visualizations.
- **shadcn/ui**: polished, copy-owned UI components built on Tailwind CSS and Radix primitives.

## 3. Why Vite + React + TypeScript

Argus-IDS already exposes a REST API from FastAPI, so the frontend does not need to be tied to Streamlit. React can call the backend endpoints directly and gives more control over layout, interaction design, reusable components, and dashboard polish.

Vite is a better fit than Next.js for the first production-quality frontend because Argus-IDS does not currently need SSR, SEO-oriented public pages, complex routing, or deployment-specific Next.js features. Next.js can be reconsidered later if the project needs auth-heavy routing, server rendering, public documentation pages, or Vercel-style deployment.

## 4. UI/UX Goals

- Make the dashboard operational and scannable: current health, latest alerts, recent simulations, and model status should be easy to read quickly.
- Keep workflows explicit: prediction, simulation, alert review, and threshold inspection should each have a clear page.
- Avoid hiding backend behavior: show useful request errors, empty states, timestamps, and backend connection state.
- Prefer compact dashboard layouts over marketing-style pages.
- Build incrementally so each step teaches one part of the stack.

## 5. App Layout and Navigation

Use a simple single-page React app with either a left sidebar or a top navigation bar. A sidebar is preferred once there are more than four pages because this is an operational dashboard.

Recommended pages:

- **Dashboard**: overview of backend health, latest alert summary, latest simulation summary, and severity distribution.
- **Predict**: run a manual JSON prediction or ask the backend for a random sample.
- **Simulations**: run a sliding-window simulation and inspect recent simulation results.
- **Alerts**: inspect recent alert log entries with filtering and severity badges.
- **Model Metrics**: evaluate threshold metrics from the backend.
- **Settings**: configure or inspect the backend URL used by the frontend.

The main content area should use restrained spacing, compact metric blocks, tables, and charts. Avoid nested cards and avoid large decorative sections.

## 6. Page Workflows

### Dashboard

- Call `GET /health` to show whether the backend is reachable.
- Call `GET /alerts` to show the latest alert count, recent severities, and newest alert timestamp.
- Call `GET /simulations` to show the most recent simulation result.
- Use Recharts for a small severity distribution chart when alert or simulation data exists.
- Empty state: explain that alerts appear after prediction calls and simulations appear after running a simulation.

### Predict

- Provide a JSON input area for raw feature payloads.
- Submit manual payloads to `POST /predict` as `{ "features": { ... } }`.
- Provide a "Random sample" action that calls `POST /predict/random`.
- Render prediction, severity, confidence, anomaly score, timestamp, and SHAP top features.
- Use a horizontal bar chart for SHAP feature impacts.
- Show malformed JSON errors before calling the backend.

### Simulations

- Provide a numeric `window_size` input.
- Submit to `POST /simulate` as `{ "window_size": number }`.
- Refresh recent simulations from `GET /simulations`.
- Render simulation timestamp, window size, attack count, anomaly count, mean risk score, severity, and alert-triggered status.
- Use a line chart for recent `mean_risk_score` values and a bar chart for severity counts.

### Alerts

- Fetch alert history with `GET /alerts`.
- Render a table with timestamp, prediction, severity, confidence, anomaly score, and top SHAP features.
- Add local filters for severity and prediction.
- Use severity badges for `LOW`, `MEDIUM`, `HIGH`, and `ANOMALY`.
- Empty state: explain that the backend stores only recent in-memory alerts and entries appear after `/predict` or `/predict/random`.

### Model Metrics

- Provide a threshold input or slider from `0.0` to `1.0`.
- Call `GET /model/threshold?threshold=...`.
- Render precision, recall, F1 score, support, total, and a confusion matrix.
- Handle backend validation errors for thresholds outside the allowed range.

### Settings

- Display the current backend base URL.
- Allow local editing of the backend URL during development.
- Explain that Vite builds should read the default from `VITE_ARGUS_BACKEND_URL`.

## 7. Backend API Contract

The frontend should treat the FastAPI backend as the source of truth for prediction, explainability, simulations, alerts, and threshold metrics.

### `GET /health`

Response:

```ts
type HealthResponse = {
  status: "ok";
};
```

### `POST /predict`

Request:

```ts
type PredictRequest = {
  features: Record<string, number>;
};
```

Response:

```ts
type ShapFeature = {
  feature: string;
  impact: number;
};

type PredictResponse = {
  prediction: string;
  severity: "LOW" | "MEDIUM" | "HIGH" | "ANOMALY" | string;
  anomaly_score: number;
  confidence: number;
  shap_top_features: ShapFeature[];
  timestamp: string;
};
```

### `POST /predict/random`

Response:

```ts
type PredictRandomResponse = PredictResponse & {
  raw_features: Record<string, number>;
};
```

### `POST /explain`

Request shape is the same as `POST /predict`.

Response:

```ts
type ExplainResponse = {
  feature_contributions: Record<string, number>;
  top_features: ShapFeature[];
  explanation_text: string;
};
```

### `GET /alerts`

Response:

```ts
type AlertEntry = {
  timestamp: string;
  prediction: string;
  severity: string;
  confidence: number;
  anomaly_score: number;
  shap_top_features: ShapFeature[];
};

type AlertsResponse = {
  alerts: AlertEntry[];
  total: number;
};
```

### `POST /simulate`

Request:

```ts
type SimulateRequest = {
  window_size: number;
};
```

Response:

```ts
type SimulateResponse = {
  timestamp: string;
  window_size: number;
  attack_count: number;
  anomaly_count: number;
  mean_risk_score: number;
  severity: string;
  alert_triggered: boolean;
};
```

### `GET /simulations`

Response:

```ts
type SimulationsResponse = {
  simulations: SimulateResponse[];
  total: number;
};
```

### `GET /model/threshold?threshold=0.5`

Response:

```ts
type ThresholdMetricsResponse = {
  threshold: number;
  confusion_matrix: number[][];
  precision: number;
  recall: number;
  f1_score: number;
  support: number;
  total: number;
  tn: number;
  fp: number;
  fn: number;
  tp: number;
};
```

## 8. Data Fetching Strategy

Start with a small typed API client, then add TanStack Query where calls are repeated, refetchable, or shared across pages.

Recommended query keys:

- `["health"]`
- `["alerts"]`
- `["simulations"]`
- `["thresholdMetrics", threshold]`

Recommended mutations:

- `predictPacket` for `POST /predict`
- `predictRandomPacket` for `POST /predict/random`
- `runSimulation` for `POST /simulate`
- `explainPacket` for `POST /explain` if the Predict page separates prediction from explanation

After successful prediction or simulation mutations, invalidate `["alerts"]` and/or `["simulations"]` so visible dashboard data stays current.

## 9. Component Structure

Recommended high-level structure once the React app is scaffolded:

```text
frontend/
└── src/
    ├── api/
    │   ├── client.ts
    │   └── types.ts
    ├── components/
    │   ├── AppShell.tsx
    │   ├── BackendStatus.tsx
    │   ├── SeverityBadge.tsx
    │   ├── MetricTile.tsx
    │   ├── ShapBarChart.tsx
    │   ├── AlertsTable.tsx
    │   └── ConfusionMatrix.tsx
    ├── hooks/
    │   ├── useHealth.ts
    │   ├── useAlerts.ts
    │   ├── useSimulations.ts
    │   └── useThresholdMetrics.ts
    ├── lib/
    │   └── config.ts
    ├── pages/
    │   ├── DashboardPage.tsx
    │   ├── PredictPage.tsx
    │   ├── SimulationsPage.tsx
    │   ├── AlertsPage.tsx
    │   ├── ModelMetricsPage.tsx
    │   └── SettingsPage.tsx
    ├── App.tsx
    └── main.tsx
```

Keep the first implementation small. Only split components when repeated behavior or page complexity justifies it.

## 10. Chart and Visualization Strategy

Use Recharts for visualizations that are supported by current backend data:

- SHAP top features: horizontal bar chart using `impact`.
- Alert severity mix: bar chart or compact pie chart from `GET /alerts`.
- Alert confidence distribution: histogram-style bar chart if enough alerts exist.
- Simulation risk over time: line chart using `mean_risk_score`.
- Simulation severity counts: bar chart.
- Threshold metrics: confusion matrix grid plus metric tiles for precision, recall, and F1.

Do not build ROC, precision-recall, calibration, or static model artifact charts until the backend exposes those artifacts or data through HTTP.

## 11. shadcn/ui Usage Plan

Add shadcn/ui after the first plain React pages are understandable. Use it for practical dashboard controls:

- `Button` for page actions.
- `Input`, `Textarea`, and `Slider` for forms.
- `Table` for alerts and simulations.
- `Badge` for severity.
- `Tabs` only where a page has truly separate views.
- `Alert` for backend errors and validation messages.
- `Dialog` only for details that would clutter the main page.
- `Skeleton` for loading states.

Avoid adding a large design system all at once. Install only the components needed by the current phase.

## 12. State Management

- Use TanStack Query for backend/server state.
- Use React local state for form inputs, selected filters, selected threshold, selected rows, and temporary JSON text.
- Use URL state only if shareable filters or deep links become useful.
- Avoid Redux, Zustand, or other global state libraries until there is real cross-page client state that TanStack Query and local state cannot handle cleanly.

## 13. Error, Loading, and Empty States

- Show loading states for health, alerts, simulations, and threshold metrics.
- Show a clear backend-unreachable message when requests fail due to network or CORS issues.
- Show backend error details when FastAPI returns useful `detail` messages.
- Validate manual prediction JSON before sending a request.
- Treat empty alerts and simulations as normal states, not failures.
- Keep stale data visible during refetches when TanStack Query can do so without confusing the user.

## 14. Environment Variables

The project-level concept is `ARGUS_BACKEND_URL`, but Vite only exposes client-side environment variables with the `VITE_` prefix. The React frontend should therefore use:

```text
VITE_ARGUS_BACKEND_URL=http://localhost:8000
```

Recommended config helper:

```ts
export const backendUrl =
  import.meta.env.VITE_ARGUS_BACKEND_URL ?? "http://localhost:8000";
```

The Settings page may allow editing the backend URL locally during development, but the environment variable should remain the default source.

## 15. CORS and Backend Assumptions

The backend controls browser access through `ARGUS_ALLOWED_ORIGINS` in `backend/api/main.py`.

For local Vite development, include the Vite origin:

```bash
ARGUS_ALLOWED_ORIGINS=http://localhost:5173
```

Backend assumptions:

- FastAPI remains the source of truth for all model behavior.
- The frontend should not reimplement prediction, SHAP, simulation, threshold metrics, or severity decisions.
- Alerts and simulations are currently in-memory and capped by the backend.
- The frontend should gracefully handle a fresh backend process with no alerts or simulations.

## 16. Development Phases

### Phase 1: Vite + React + TypeScript

- Scaffold the app.
- Add basic routes or local page switching.
- Add the app shell and navigation.
- Render static placeholders for each planned page.

### Phase 2: API Client Layer

- Add TypeScript response/request types matching `backend/api/schemas.py`.
- Add a small `fetchJson` helper with base URL handling.
- Implement direct calls for `/health`, `/alerts`, `/simulations`, and `/predict/random`.

### Phase 3: TanStack Query

- Add query hooks for health, alerts, simulations, and threshold metrics.
- Add mutations for prediction and simulation.
- Invalidate relevant queries after mutations.

### Phase 4: Visualizations

- Add Recharts for SHAP top features.
- Add alert severity and simulation risk charts.
- Add threshold metrics visualization.

### Phase 5: shadcn/ui Polish

- Replace plain controls with shadcn/ui components progressively.
- Add consistent table, badge, input, button, alert, and skeleton patterns.
- Keep the dashboard compact and practical.

## 17. Current Backend Limitations and Out of Scope

Current backend limitations to respect:

- There is no `GET /simulations/{id}` endpoint.
- `POST /simulate` currently accepts only `window_size`.
- Alerts are in-memory and capped at 50 entries.
- Simulations are in-memory and capped at 50 entries.
- Model chart PNG artifacts exist in `backend/model/`, but they are not currently exposed by HTTP endpoints.

Out of scope for the first React frontend:

- Authentication and role-based access control.
- WebSockets or real-time streaming.
- Persistent alert storage.
- Editing model thresholds on the backend.
- Uploading datasets from the frontend.
- Reimplementing ML inference in the browser.
- SSR, SEO pages, public marketing pages, or Next.js migration.
- Full model artifact browsing unless the backend exposes supported endpoints.

## 18. Future Acceptance Criteria

The first usable React dashboard should satisfy these checks:

- Backend URL is configurable through `VITE_ARGUS_BACKEND_URL`.
- `/health` status renders clearly.
- Random prediction renders prediction, severity, confidence, anomaly score, timestamp, and SHAP features.
- Manual prediction handles malformed JSON and backend validation errors.
- Alerts and simulations pages handle empty arrays without errors.
- Simulation can run with a selected `window_size`.
- Threshold metrics page handles valid thresholds and backend validation errors.
- Local CORS setup is documented for Vite development.
