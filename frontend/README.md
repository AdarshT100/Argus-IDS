# Argus-IDS Frontend

Vite + React + TypeScript frontend for the Argus-IDS dashboard.

## Local Development

```bash
npm install
npm run dev
```

The Vite dev server normally runs on `http://localhost:5173`.

## Backend URL

Set the backend base URL with:

```bash
VITE_ARGUS_BACKEND_URL=http://localhost:8000
```

If unset, the frontend falls back to `http://localhost:8000`.

## Available Scripts

```bash
npm run dev
npm run build
npm run lint
npm run preview
```

Phase 1 currently includes the app shell and placeholder pages only. API calls, TanStack Query, charts, and shadcn/ui are tracked in `../frontendTodo.md`.
