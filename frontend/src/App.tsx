import { useMemo, useState, type ReactNode } from 'react'
import './App.css'
import { Button } from './components/ui/button'
import { backendUrl } from './lib/config'
import AlertsPage from './pages/Alerts'
import DashboardPage from './pages/Dashboard'
import MetricsPage from './pages/Metrics'
import PredictPage from './pages/Predict'
import SettingsPage from './pages/Settings'
import SimulationsPage from './pages/Simulations'

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

const pages: Page[] = [
  { key: 'dashboard', label: 'Dashboard', eyebrow: 'Overview', title: 'Operational Insights' },
  { key: 'predict', label: 'Predict', eyebrow: 'Single packet', title: 'Manual and random prediction' },
  { key: 'simulations', label: 'Simulations', eyebrow: 'Window analysis', title: 'Sliding-window simulation' },
  { key: 'alerts', label: 'Alerts', eyebrow: 'Detection log', title: 'Recent alert review' },
  { key: 'metrics', label: 'Model Metrics', eyebrow: 'Threshold view', title: 'Threshold metrics' },
  { key: 'settings', label: 'Settings', eyebrow: 'Configuration', title: 'Frontend runtime settings' },
]

const pageComponents: Record<PageKey, ReactNode> = {
  dashboard: <DashboardPage />,
  predict: <PredictPage />,
  simulations: <SimulationsPage />,
  alerts: <AlertsPage />,
  metrics: <MetricsPage />,
  settings: <SettingsPage />,
}

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
            <Button
              key={item.key}
              aria-current={item.key === activePage ? 'page' : undefined}
              className={item.key === activePage ? 'active' : undefined}
              variant="ghost"
              onClick={() => setActivePage(item.key)}
            >
              {item.label}
            </Button>
          ))}
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">{page.eyebrow}</p>
            <h1>{page.title}</h1>
          </div>
          <div className="status-pill">
            <span className="status-dot" aria-hidden="true" />
            Backend URL: {backendUrl}
          </div>
        </header>

        {pageComponents[activePage]}
      </main>
    </div>
  )
}

export default App
