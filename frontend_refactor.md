# Frontend Refactor Instructions
# Argus-IDS — App.tsx Decomposition
# Complete this entirely before touching the Model Overview page.

---

## 0. Ground Rules

- Do NOT change any functionality. This is a pure structural refactor.
- Do NOT rename any functions, types, or variables.
- Do NOT change any CSS classes or styling.
- Do NOT install new dependencies.
- Do NOT modify anything inside `src/lib/` or `src/components/ui/`.
- After each step, the app must run and behave identically to before.
- The final `App.tsx` should be under 100 lines.

---

## 1. Create the folder structure

Create these directories if they do not exist:

```
src/
  pages/
  components/shared/
```

`src/pages/` — one file per page (Dashboard, Predict, etc.)
`src/components/shared/` — reusable non-shadcn components that are
currently defined in App.tsx and used across multiple pages.

Do not touch:
- `src/lib/` — api.ts, config.ts, queries.ts, types.ts, utils.ts
- `src/components/ui/` — all shadcn primitives (alert, badge, button, etc.)

---

## 2. Extract shared components

These components are currently defined in `App.tsx` and used by multiple
pages. Move them to `src/components/shared/` as individual files.

### `src/components/shared/Panel.tsx`
Extract the `Panel` component and its prop type.

```typescript
// Exports: Panel
// Props: { title: string; eyebrow: string; children: ReactNode }
```

### `src/components/shared/MetricCard.tsx`
Extract the `MetricCard` component and its prop type.

```typescript
// Exports: MetricCard
// Props: { label: string; value: string; detail: string }
```

### `src/components/shared/QueryState.tsx`
Extract the `QueryState` component and its prop type.

```typescript
// Exports: QueryState
// Props: { isLoading: boolean; error: unknown; empty: boolean; emptyText: string; children: ReactNode }
```

### `src/components/shared/SeverityBadge.tsx`
Extract the `SeverityBadge` component.
Also move `severityVariant()` helper into this file since it is only
used by `SeverityBadge`.

```typescript
// Exports: SeverityBadge
// Props: { severity: Severity }
// Internal: severityVariant()
```

### `src/components/shared/EmptyState.tsx`
Extract the `EmptyState` component.

```typescript
// Exports: EmptyState
// Props: { text: string }
```

### `src/components/shared/LoadingState.tsx`
Extract the `LoadingState` component.

```typescript
// Exports: LoadingState
// Props: none
```

### `src/components/shared/index.ts`
Create a barrel export file so pages can import from one place:

```typescript
export { Panel } from './Panel'
export { MetricCard } from './MetricCard'
export { QueryState } from './QueryState'
export { SeverityBadge } from './SeverityBadge'
export { EmptyState } from './EmptyState'
export { LoadingState } from './LoadingState'
```

---

## 3. Extract chart components

These chart components are currently defined in `App.tsx`. Move them to
`src/components/shared/` as they may be reused by future pages.

### `src/components/shared/ShapImpactChart.tsx`
Extract `ShapImpactChart`.
Needs: `chartColors`, `chartMargin`, `formatCompactNumber`,
`formatTooltipNumber` — import these from `src/lib/constants.ts`
(created in Step 5).

```typescript
// Exports: ShapImpactChart
// Props: { features: ShapFeature[] }
```

### `src/components/shared/AlertSeverityChart.tsx`
Extract `AlertSeverityChart`.
Needs: `chartColors`, `severityColor`, `severityOrder`.

```typescript
// Exports: AlertSeverityChart
// Props: { alerts: AlertEntry[] }
```

### `src/components/shared/SimulationRiskChart.tsx`
Extract `SimulationRiskChart`.
Needs: `chartColors`, `chartMargin`, `formatSimulationTooltip`,
`formatPercentTick`, `formatCompactNumber`, `shortDate`.

```typescript
// Exports: SimulationRiskChart
// Props: { simulations: SimulateResponse[] }
```

Add these to the barrel export in `src/components/shared/index.ts`.

---

## 4. Extract page-specific components

These components are used by only one page. Co-locate them with their
page in `src/pages/` rather than in shared.

### Used only by PredictPage:
- `PredictionDetails`
- `ExplanationText`
- `TopFeatures`

Keep these in `src/pages/Predict.tsx` (defined in the same file or as
non-exported functions within it).

### Used only by SimulationsPage:
- `SimulationDetails`
- `SimulationTable`

Keep these in `src/pages/Simulations.tsx`.

### Used only by AlertsPage:
- `AlertList`
- `AlertTable`

Keep these in `src/pages/Alerts.tsx`.

### Used only by MetricsPage:
- `ConfusionMatrix`
- `ThresholdMetricsChart`

Keep these in `src/pages/Metrics.tsx`.

---

## 5. Extract constants and formatters

Currently in `App.tsx`, these are pure utilities with no JSX.
Move them to `src/lib/constants.ts` and check `src/lib/utils.ts`
— some formatters may already exist there. Do not duplicate.

### `src/lib/constants.ts`
Move these from `App.tsx`:

```typescript
export const chartColors = {
  green: '#12b76a',
  amber: '#f79009',
  red: '#f04438',
  teal: '#0f766e',
  gray: '#667085',
}

export const severityOrder = ['LOW', 'MEDIUM', 'HIGH', 'ANOMALY']
export const chartMargin = { top: 8, right: 20, bottom: 8, left: 8 }

export function severityColor(severity: string): string { ... }
```

Move these formatter functions from `App.tsx` to `src/lib/utils.ts`
if not already present:

```
formatPercent
formatPercentTick
formatNumber
formatReadableFeatureValue
formatExplanationText
formatCompactNumber
formatTooltipNumber
formatSimulationTooltip
formatTooltipPercent
formatDate
shortDate
formatTopFeature
errorMessage
uniqueOptions
isPlainObject
parseFeatureJson      ← used only by PredictPage, can stay in Predict.tsx
validateThreshold     ← used only by MetricsPage, can stay in Metrics.tsx
```

---

## 6. Create page files

Create one file per page in `src/pages/`. Each file exports a single
default component. Import shared components from
`src/components/shared/` and utilities from `src/lib/`.

### `src/pages/Dashboard.tsx`
Move `DashboardPage` function here. Rename export to `DashboardPage`.
Imports needed: `Panel`, `MetricCard`, `QueryState`, `AlertSeverityChart`,
`SimulationRiskChart`, `AlertList`, `SimulationDetails` (move here too),
all relevant queries, formatters.

### `src/pages/Predict.tsx`
Move `PredictPage` here. Keep `PredictionDetails`, `ExplanationText`,
`TopFeatures`, `parseFeatureJson`, `sampleFeatureJson` in this file.

### `src/pages/Simulations.tsx`
Move `SimulationsPage` here. Keep `SimulationDetails`, `SimulationTable`
in this file.

### `src/pages/Alerts.tsx`
Move `AlertsPage` here. Keep `AlertList`, `AlertTable` in this file.

### `src/pages/Metrics.tsx`
Move `MetricsPage` here. Keep `ConfusionMatrix`, `ThresholdMetricsChart`,
`validateThreshold` in this file.

### `src/pages/Settings.tsx`
Move `SettingsPage` here.

---

## 7. Rewrite App.tsx

After all extractions are done, `App.tsx` should contain only:

1. The `PageKey` type
2. The `Page` type
3. The `pages` array
4. The `App` function with sidebar and routing logic
5. Imports for all page components

It should look roughly like this:

```typescript
import { useMemo, useState } from 'react'
import { Button } from './components/ui/button'
import { DashboardPage } from './pages/Dashboard'
import { PredictPage } from './pages/Predict'
import { SimulationsPage } from './pages/Simulations'
import { AlertsPage } from './pages/Alerts'
import { MetricsPage } from './pages/Metrics'
import { SettingsPage } from './pages/Settings'
import { backendUrl } from './lib/config'
import './App.css'

type PageKey =
  | 'dashboard'
  | 'predict'
  | 'simulations'
  | 'alerts'
  | 'metrics'
  | 'settings'

type Page = {
  key: PageKey
  label: string
  eyebrow: string
  title: string
}

const pages: Page[] = [ ... ] // same as before

function App() {
  const [activePage, setActivePage] = useState<PageKey>('dashboard')
  const page = useMemo(
    () => pages.find((item) => item.key === activePage) ?? pages[0],
    [activePage],
  )

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        ...sidebar unchanged...
      </aside>
      <main className="workspace">
        <header className="topbar">...</header>
        {activePage === 'dashboard'    && <DashboardPage />}
        {activePage === 'predict'      && <PredictPage />}
        {activePage === 'simulations'  && <SimulationsPage />}
        {activePage === 'alerts'       && <AlertsPage />}
        {activePage === 'metrics'      && <MetricsPage />}
        {activePage === 'settings'     && <SettingsPage />}
      </main>
    </div>
  )
}

export default App
```

---

## 8. Final folder structure after refactor

```
src/
  components/
    ui/                        ← untouched (shadcn primitives)
      alert.tsx
      badge.tsx
      button.tsx
      input.tsx
      select.tsx
      skeleton.tsx
      table.tsx
      textarea.tsx
    shared/                    ← NEW — reusable non-shadcn components
      Panel.tsx
      MetricCard.tsx
      QueryState.tsx
      SeverityBadge.tsx
      EmptyState.tsx
      LoadingState.tsx
      ShapImpactChart.tsx
      AlertSeverityChart.tsx
      SimulationRiskChart.tsx
      index.ts
  lib/                         ← mostly untouched
    api.ts
    config.ts
    constants.ts               ← NEW — chartColors, severityOrder, chartMargin, severityColor
    queries.ts
    types.ts
    utils.ts                   ← extended with formatters from App.tsx
  pages/                       ← NEW — one file per page
    Dashboard.tsx
    Predict.tsx
    Simulations.tsx
    Alerts.tsx
    Metrics.tsx
    Settings.tsx
  assets/
  App.css
  App.tsx                      ← ~80 lines after refactor
  index.css
  main.tsx
```

---

## 9. Verification checklist

Before marking this refactor complete, verify:

- [ ] `npm run dev` starts without errors
- [ ] All 6 existing pages render and function identically to before
- [ ] No TypeScript errors (`npm run typecheck` or `tsc --noEmit`)
- [ ] `App.tsx` is under 100 lines
- [ ] No logic or formatting function remains defined in `App.tsx`
- [ ] No page component remains defined in `App.tsx`
- [ ] `src/lib/` and `src/components/ui/` are unchanged
- [ ] The sidebar still renders all 6 nav items correctly
- [ ] Charts on Dashboard, Predict, Simulations, Alerts, and Metrics pages still render

---
