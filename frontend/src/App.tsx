import { useMemo, useState } from 'react'
import './App.css'
import { backendUrl } from './lib/config'

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
  description: string
  nextSteps: string[]
}

const pages: Page[] = [
  {
    key: 'dashboard',
    label: 'Dashboard',
    eyebrow: 'Overview',
    title: 'Operational snapshot',
    description:
      'The dashboard will summarize backend health, recent alerts, recent simulations, and severity distribution.',
    nextSteps: [
      'Connect GET /health for backend status.',
      'Load GET /alerts for latest alert counts.',
      'Load GET /simulations for recent simulation results.',
    ],
  },
  {
    key: 'predict',
    label: 'Predict',
    eyebrow: 'Single packet',
    title: 'Manual and random prediction',
    description:
      'This page will accept raw feature JSON, request random backend samples, and show prediction confidence with SHAP top features.',
    nextSteps: [
      'Add JSON validation before POST /predict.',
      'Add POST /predict/random action.',
      'Render severity, confidence, anomaly score, and SHAP features.',
    ],
  },
  {
    key: 'simulations',
    label: 'Simulations',
    eyebrow: 'Window analysis',
    title: 'Sliding-window simulation',
    description:
      'This page will run backend simulations and compare recent windows by risk, attack count, anomaly count, and severity.',
    nextSteps: [
      'Add window size input for POST /simulate.',
      'Refresh recent runs from GET /simulations.',
      'Prepare Recharts views for mean risk and severity.',
    ],
  },
  {
    key: 'alerts',
    label: 'Alerts',
    eyebrow: 'Detection log',
    title: 'Recent alert review',
    description:
      'This page will show the backend alert log with local filtering, severity badges, timestamps, and SHAP summaries.',
    nextSteps: [
      'Load GET /alerts with empty-state handling.',
      'Add severity and prediction filters.',
      'Render compact rows for the capped in-memory alert log.',
    ],
  },
  {
    key: 'metrics',
    label: 'Model Metrics',
    eyebrow: 'Threshold view',
    title: 'Threshold metrics',
    description:
      'This page will inspect precision, recall, F1, support, and the confusion matrix for a selected threshold.',
    nextSteps: [
      'Add threshold input from 0.0 to 1.0.',
      'Call GET /model/threshold?threshold=...',
      'Render confusion matrix and metric tiles.',
    ],
  },
  {
    key: 'settings',
    label: 'Settings',
    eyebrow: 'Configuration',
    title: 'Frontend runtime settings',
    description:
      'This page records frontend assumptions and the backend base URL that future API calls will use.',
    nextSteps: [
      'Read VITE_ARGUS_BACKEND_URL at build time.',
      'Keep http://localhost:8000 as the local fallback.',
      'Document CORS expectation for http://localhost:5173.',
    ],
  },
]

function App() {
  const [activePage, setActivePage] = useState<PageKey>('dashboard')

  const page = useMemo(
    () => pages.find((item) => item.key === activePage) ?? pages[0],
    [activePage],
  )

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-block">
          <span className="brand-mark">A</span>
          <div>
            <p className="brand-name">Argus-IDS</p>
            <p className="brand-subtitle">IoT intrusion dashboard</p>
          </div>
        </div>

        <nav className="nav-list">
          {pages.map((item) => (
            <button
              key={item.key}
              className={item.key === activePage ? 'nav-item active' : 'nav-item'}
              type="button"
              onClick={() => setActivePage(item.key)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Phase 1 frontend scaffold</p>
            <h1>{page.title}</h1>
          </div>
          <div className="status-pill">
            <span className="status-dot" aria-hidden="true" />
            Backend URL: {backendUrl}
          </div>
        </header>

        <section className="summary-grid" aria-label="Phase 1 status">
          <article className="metric-card">
            <span className="metric-label">Frontend</span>
            <strong>Vite + React</strong>
            <span>TypeScript scaffold</span>
          </article>
          <article className="metric-card">
            <span className="metric-label">API calls</span>
            <strong>Deferred</strong>
            <span>Planned for Phase 2</span>
          </article>
          <article className="metric-card">
            <span className="metric-label">Charts</span>
            <strong>Deferred</strong>
            <span>Planned for Phase 5</span>
          </article>
        </section>

        <section className="page-panel">
          <p className="eyebrow">{page.eyebrow}</p>
          <h2>{page.label}</h2>
          <p className="page-description">{page.description}</p>

          <div className="next-block">
            <h3>Next implementation steps</h3>
            <ul>
              {page.nextSteps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
