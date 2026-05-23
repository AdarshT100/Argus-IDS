# Argus-IDS Frontend Build Todo

This checklist tracks the phased React frontend build. Update it after each phase so the current state and next work are visible from the project root.

## Phase 1: Vite React TypeScript Scaffold

Status: Complete

- [x] Scaffold Vite + React + TypeScript app directly under `frontend/`.
- [x] Install default npm dependencies.
- [x] Replace starter screen with Argus-IDS app shell.
- [x] Add placeholder pages: Dashboard, Predict, Simulations, Alerts, Model Metrics, Settings.
- [x] Add backend URL placeholder using `VITE_ARGUS_BACKEND_URL` with `http://localhost:8000` fallback.
- [x] Verify production build with `npm run build`.
- [x] Confirm no old Streamlit references remain.

## Phase 2: Typed API Client

Status: Not started

- [ ] Add API request/response types matching `backend/api/schemas.py`.
- [ ] Add shared backend config helper.
- [ ] Add fetch helper with backend error handling.
- [ ] Add client methods for health, alerts, simulations, prediction, explanation, and threshold metrics.

## Phase 3: TanStack Query

Status: Not started

- [ ] Install TanStack Query.
- [ ] Add query hooks for health, alerts, simulations, and threshold metrics.
- [ ] Add mutation hooks for prediction, random prediction, and simulation.
- [ ] Invalidate alerts and simulations after relevant mutations.

## Phase 4: API-Backed Pages

Status: Not started

- [ ] Dashboard renders backend health, alert summary, and simulation summary.
- [ ] Predict page supports JSON input and random sample prediction.
- [ ] Simulations page runs simulations and lists recent runs.
- [ ] Alerts page renders recent alerts with local filtering.
- [ ] Model Metrics page renders threshold metrics and validation errors.

## Phase 5: Charts

Status: Not started

- [ ] Install Recharts.
- [ ] Add SHAP feature impact chart.
- [ ] Add alert severity visualization.
- [ ] Add simulation risk visualization.
- [ ] Add threshold metrics visualization.

## Phase 6: UI Polish

Status: Not started

- [ ] Add shadcn/ui incrementally.
- [ ] Replace plain controls with polished buttons, inputs, textareas, tables, badges, alerts, and skeletons.
- [ ] Review responsive layout on desktop and mobile.
- [ ] Update `frontendDesign.md` if implementation decisions change.

## Current Notes

- The previous Streamlit frontend has been removed.
- Phase 1 intentionally avoids backend calls, TanStack Query, Recharts, Tailwind, and shadcn/ui.
- Phase 1 build and lint pass from `frontend/`.
- `npm install` completed with Node engine warnings because local Node is `v23.11.0`; installed packages prefer Node `^20.19.0`, `^22.13.0`, or `>=24`.
- Frontend dev origin is expected to be `http://localhost:5173`.
