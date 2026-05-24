import { useMemo, useState, type FormEvent, type ReactNode } from 'react'
import './App.css'
import { backendUrl } from './lib/config'
import {
  useAlertsQuery,
  useHealthQuery,
  usePredictMutation,
  usePredictRandomMutation,
  useSimulationMutation,
  useSimulationsQuery,
  useThresholdMetricsQuery,
} from './lib/queries'
import type {
  AlertEntry,
  PredictRandomResponse,
  PredictResponse,
  Severity,
  ShapFeature,
  SimulateResponse,
} from './lib/types'

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

type ParsedFeatures =
  | { ok: true; value: Record<string, number> }
  | { ok: false; error: string }

const pages: Page[] = [
  {
    key: 'dashboard',
    label: 'Dashboard',
    eyebrow: 'Overview',
    title: 'Operational snapshot',
  },
  {
    key: 'predict',
    label: 'Predict',
    eyebrow: 'Single packet',
    title: 'Manual and random prediction',
  },
  {
    key: 'simulations',
    label: 'Simulations',
    eyebrow: 'Window analysis',
    title: 'Sliding-window simulation',
  },
  {
    key: 'alerts',
    label: 'Alerts',
    eyebrow: 'Detection log',
    title: 'Recent alert review',
  },
  {
    key: 'metrics',
    label: 'Model Metrics',
    eyebrow: 'Threshold view',
    title: 'Threshold metrics',
  },
  {
    key: 'settings',
    label: 'Settings',
    eyebrow: 'Configuration',
    title: 'Frontend runtime settings',
  },
]

const sampleFeatureJson = JSON.stringify(
  {
    'Flow Duration': 123456,
    'Total Fwd Packets': 10,
    'Total Backward Packets': 8,
    'Flow Bytes/s': 2345.7,
    'Flow Packets/s': 14.8,
  },
  null,
  2,
)

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
            <p className="eyebrow">{page.eyebrow}</p>
            <h1>{page.title}</h1>
          </div>
          <div className="status-pill">
            <span className="status-dot" aria-hidden="true" />
            Backend URL: {backendUrl}
          </div>
        </header>

        {activePage === 'dashboard' && <DashboardPage />}
        {activePage === 'predict' && <PredictPage />}
        {activePage === 'simulations' && <SimulationsPage />}
        {activePage === 'alerts' && <AlertsPage />}
        {activePage === 'metrics' && <MetricsPage />}
        {activePage === 'settings' && <SettingsPage />}
      </main>
    </div>
  )
}

function DashboardPage() {
  const healthQuery = useHealthQuery()
  const alertsQuery = useAlertsQuery()
  const simulationsQuery = useSimulationsQuery()

  const alerts = alertsQuery.data?.alerts ?? []
  const simulations = simulationsQuery.data?.simulations ?? []
  const highAlerts = alerts.filter((alert) => alert.severity === 'HIGH').length
  const anomalyAlerts = alerts.filter(
    (alert) => alert.severity === 'ANOMALY',
  ).length
  const triggeredSimulations = simulations.filter(
    (simulation) => simulation.alert_triggered,
  ).length
  const latestSimulation = simulations[0]

  return (
    <>
      <section className="summary-grid" aria-label="Backend summary">
        <MetricCard
          label="Backend"
          value={healthQuery.data?.status === 'ok' ? 'Online' : 'Unknown'}
          detail={
            healthQuery.isError
              ? errorMessage(healthQuery.error)
              : 'GET /health status'
          }
        />
        <MetricCard
          label="Alerts"
          value={alertsQuery.isLoading ? 'Loading' : alerts.length.toString()}
          detail={`${highAlerts} high, ${anomalyAlerts} anomaly`}
        />
        <MetricCard
          label="Simulations"
          value={
            simulationsQuery.isLoading ? 'Loading' : simulations.length.toString()
          }
          detail={`${triggeredSimulations} triggered alerts`}
        />
      </section>

      <section className="content-grid two-column">
        <Panel title="Recent alerts" eyebrow="Latest detections">
          <QueryState
            isLoading={alertsQuery.isLoading}
            error={alertsQuery.error}
            empty={!alerts.length}
            emptyText="No alerts returned by the backend yet."
          >
            <AlertList alerts={alerts.slice(0, 5)} />
          </QueryState>
        </Panel>

        <Panel title="Simulation summary" eyebrow="Latest run">
          <QueryState
            isLoading={simulationsQuery.isLoading}
            error={simulationsQuery.error}
            empty={!latestSimulation}
            emptyText="No simulation runs returned by the backend yet."
          >
            {latestSimulation && <SimulationDetails simulation={latestSimulation} />}
          </QueryState>
        </Panel>
      </section>
    </>
  )
}

function PredictPage() {
  const [featureJson, setFeatureJson] = useState(sampleFeatureJson)
  const [validationError, setValidationError] = useState('')
  const [result, setResult] = useState<
    PredictResponse | PredictRandomResponse | null
  >(null)
  const predictMutation = usePredictMutation()
  const randomMutation = usePredictRandomMutation()

  function submitPrediction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const parsed = parseFeatureJson(featureJson)

    if (!parsed.ok) {
      setValidationError(parsed.error)
      return
    }

    setValidationError('')
    predictMutation.mutate(
      { features: parsed.value },
      {
        onSuccess: setResult,
      },
    )
  }

  function runRandomPrediction() {
    setValidationError('')
    randomMutation.mutate(undefined, {
      onSuccess: (response) => {
        setResult(response)
        setFeatureJson(JSON.stringify(response.raw_features, null, 2))
      },
    })
  }

  const activeError =
    validationError ||
    errorMessage(predictMutation.error) ||
    errorMessage(randomMutation.error)

  return (
    <section className="content-grid two-column wide-left">
      <Panel title="Feature JSON" eyebrow="Request body">
        <form className="form-stack" onSubmit={submitPrediction}>
          <textarea
            aria-label="Feature JSON"
            className="json-input"
            value={featureJson}
            onChange={(event) => setFeatureJson(event.target.value)}
            spellCheck={false}
          />
          {activeError && <p className="error-text">{activeError}</p>}
          <div className="button-row">
            <button
              className="primary-button"
              disabled={predictMutation.isPending}
              type="submit"
            >
              {predictMutation.isPending ? 'Predicting...' : 'Run prediction'}
            </button>
            <button
              className="secondary-button"
              disabled={randomMutation.isPending}
              type="button"
              onClick={runRandomPrediction}
            >
              {randomMutation.isPending ? 'Sampling...' : 'Random sample'}
            </button>
          </div>
        </form>
      </Panel>

      <Panel title="Prediction result" eyebrow="Model output">
        {result ? (
          <PredictionDetails result={result} />
        ) : (
          <EmptyState text="Run a manual or random prediction to inspect severity, confidence, anomaly score, and top SHAP features." />
        )}
      </Panel>
    </section>
  )
}

function SimulationsPage() {
  const [windowSize, setWindowSize] = useState('50')
  const [validationError, setValidationError] = useState('')
  const simulationsQuery = useSimulationsQuery()
  const simulationMutation = useSimulationMutation()
  const simulations = simulationsQuery.data?.simulations ?? []

  function submitSimulation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const parsedWindowSize = Number(windowSize)

    if (!Number.isInteger(parsedWindowSize) || parsedWindowSize < 1) {
      setValidationError('Window size must be a positive whole number.')
      return
    }

    setValidationError('')
    simulationMutation.mutate({ window_size: parsedWindowSize })
  }

  const activeError = validationError || errorMessage(simulationMutation.error)

  return (
    <section className="content-grid two-column">
      <Panel title="Run simulation" eyebrow="Window controls">
        <form className="form-stack compact-form" onSubmit={submitSimulation}>
          <label className="field-label" htmlFor="window-size">
            Window size
          </label>
          <input
            id="window-size"
            min="1"
            step="1"
            type="number"
            value={windowSize}
            onChange={(event) => setWindowSize(event.target.value)}
          />
          {activeError && <p className="error-text">{activeError}</p>}
          <button
            className="primary-button"
            disabled={simulationMutation.isPending}
            type="submit"
          >
            {simulationMutation.isPending ? 'Running...' : 'Run simulation'}
          </button>
        </form>

        {simulationMutation.data && (
          <div className="result-block">
            <SimulationDetails simulation={simulationMutation.data} />
          </div>
        )}
      </Panel>

      <Panel title="Recent runs" eyebrow="Backend history">
        <QueryState
          isLoading={simulationsQuery.isLoading}
          error={simulationsQuery.error}
          empty={!simulations.length}
          emptyText="No simulations returned by the backend yet."
        >
          <SimulationTable simulations={simulations} />
        </QueryState>
      </Panel>
    </section>
  )
}

function AlertsPage() {
  const [severityFilter, setSeverityFilter] = useState('ALL')
  const [predictionFilter, setPredictionFilter] = useState('ALL')
  const alertsQuery = useAlertsQuery()
  const alerts = alertsQuery.data?.alerts ?? []

  const severities = uniqueOptions(alerts.map((alert) => alert.severity))
  const predictions = uniqueOptions(alerts.map((alert) => alert.prediction))
  const filteredAlerts = alerts.filter((alert) => {
    const severityMatches =
      severityFilter === 'ALL' || alert.severity === severityFilter
    const predictionMatches =
      predictionFilter === 'ALL' || alert.prediction === predictionFilter

    return severityMatches && predictionMatches
  })

  return (
    <Panel title="Recent alerts" eyebrow="Local filters">
      <div className="filter-row">
        <label>
          Severity
          <select
            value={severityFilter}
            onChange={(event) => setSeverityFilter(event.target.value)}
          >
            <option value="ALL">All severities</option>
            {severities.map((severity) => (
              <option key={severity} value={severity}>
                {severity}
              </option>
            ))}
          </select>
        </label>
        <label>
          Prediction
          <select
            value={predictionFilter}
            onChange={(event) => setPredictionFilter(event.target.value)}
          >
            <option value="ALL">All predictions</option>
            {predictions.map((prediction) => (
              <option key={prediction} value={prediction}>
                {prediction}
              </option>
            ))}
          </select>
        </label>
        <span className="filter-count">
          {filteredAlerts.length} of {alerts.length}
        </span>
      </div>

      <QueryState
        isLoading={alertsQuery.isLoading}
        error={alertsQuery.error}
        empty={!filteredAlerts.length}
        emptyText="No alerts match the current filters."
      >
        <AlertTable alerts={filteredAlerts} />
      </QueryState>
    </Panel>
  )
}

function MetricsPage() {
  const [thresholdInput, setThresholdInput] = useState('0.5')
  const [threshold, setThreshold] = useState(0.5)
  const thresholdValidation = validateThreshold(thresholdInput)
  const metricsQuery = useThresholdMetricsQuery(threshold)

  function submitThreshold(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!thresholdValidation) {
      setThreshold(Number(thresholdInput))
    }
  }

  const metrics = metricsQuery.data

  return (
    <section className="content-grid two-column">
      <Panel title="Threshold selector" eyebrow="Validation view">
        <form className="form-stack compact-form" onSubmit={submitThreshold}>
          <label className="field-label" htmlFor="threshold">
            Threshold
          </label>
          <input
            id="threshold"
            max="1"
            min="0"
            step="0.01"
            type="number"
            value={thresholdInput}
            onChange={(event) => setThresholdInput(event.target.value)}
          />
          {thresholdValidation && (
            <p className="error-text">{thresholdValidation}</p>
          )}
          {metricsQuery.error && (
            <p className="error-text">{errorMessage(metricsQuery.error)}</p>
          )}
          <button className="primary-button" type="submit">
            Load metrics
          </button>
        </form>
      </Panel>

      <Panel title="Metrics" eyebrow={`Threshold ${threshold.toFixed(2)}`}>
        <QueryState
          isLoading={metricsQuery.isLoading}
          error={metricsQuery.error}
          empty={!metrics}
          emptyText="No threshold metrics returned by the backend."
        >
          {metrics && (
            <div className="metrics-stack">
              <div className="summary-grid compact">
                <MetricCard
                  label="Precision"
                  value={formatPercent(metrics.precision)}
                  detail={`${metrics.tp} TP, ${metrics.fp} FP`}
                />
                <MetricCard
                  label="Recall"
                  value={formatPercent(metrics.recall)}
                  detail={`${metrics.fn} FN, ${metrics.tn} TN`}
                />
                <MetricCard
                  label="F1 score"
                  value={formatPercent(metrics.f1_score)}
                  detail={`${metrics.support} support`}
                />
              </div>
              <ConfusionMatrix matrix={metrics.confusion_matrix} />
            </div>
          )}
        </QueryState>
      </Panel>
    </section>
  )
}

function SettingsPage() {
  return (
    <Panel title="Runtime settings" eyebrow="Frontend configuration">
      <dl className="settings-list">
        <div>
          <dt>Backend base URL</dt>
          <dd>{backendUrl}</dd>
        </div>
        <div>
          <dt>Local frontend origin</dt>
          <dd>http://localhost:5173</dd>
        </div>
        <div>
          <dt>API data layer</dt>
          <dd>TanStack Query with one retry and no window-focus refetch.</dd>
        </div>
      </dl>
    </Panel>
  )
}

function MetricCard({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail: string
}) {
  return (
    <article className="metric-card">
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  )
}

function Panel({
  title,
  eyebrow,
  children,
}: {
  title: string
  eyebrow: string
  children: ReactNode
}) {
  return (
    <section className="page-panel">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      {children}
    </section>
  )
}

function QueryState({
  isLoading,
  error,
  empty,
  emptyText,
  children,
}: {
  isLoading: boolean
  error: unknown
  empty: boolean
  emptyText: string
  children: ReactNode
}) {
  if (isLoading) {
    return <EmptyState text="Loading backend data..." />
  }

  if (error) {
    return <p className="error-text">{errorMessage(error)}</p>
  }

  if (empty) {
    return <EmptyState text={emptyText} />
  }

  return children
}

function PredictionDetails({
  result,
}: {
  result: PredictResponse | PredictRandomResponse
}) {
  return (
    <div className="details-stack">
      <div className="result-header">
        <SeverityBadge severity={result.severity} />
        <strong>{result.prediction}</strong>
      </div>
      <dl className="details-list">
        <div>
          <dt>Confidence</dt>
          <dd>{formatPercent(result.confidence)}</dd>
        </div>
        <div>
          <dt>Anomaly score</dt>
          <dd>{formatNumber(result.anomaly_score)}</dd>
        </div>
        <div>
          <dt>Timestamp</dt>
          <dd>{formatDate(result.timestamp)}</dd>
        </div>
      </dl>
      <TopFeatures features={result.shap_top_features} />
    </div>
  )
}

function SimulationDetails({ simulation }: { simulation: SimulateResponse }) {
  return (
    <div className="details-stack">
      <div className="result-header">
        <SeverityBadge severity={simulation.severity} />
        <strong>{simulation.alert_triggered ? 'Alert triggered' : 'No alert'}</strong>
      </div>
      <dl className="details-list">
        <div>
          <dt>Window size</dt>
          <dd>{simulation.window_size}</dd>
        </div>
        <div>
          <dt>Mean risk</dt>
          <dd>{formatNumber(simulation.mean_risk_score)}</dd>
        </div>
        <div>
          <dt>Attacks</dt>
          <dd>{simulation.attack_count}</dd>
        </div>
        <div>
          <dt>Anomalies</dt>
          <dd>{simulation.anomaly_count}</dd>
        </div>
        <div>
          <dt>Timestamp</dt>
          <dd>{formatDate(simulation.timestamp)}</dd>
        </div>
      </dl>
    </div>
  )
}

function AlertList({ alerts }: { alerts: AlertEntry[] }) {
  return (
    <div className="alert-list">
      {alerts.map((alert) => (
        <article className="alert-row" key={`${alert.timestamp}-${alert.prediction}`}>
          <div>
            <div className="result-header">
              <SeverityBadge severity={alert.severity} />
              <strong>{alert.prediction}</strong>
            </div>
            <span>{formatDate(alert.timestamp)}</span>
          </div>
          <span>{formatPercent(alert.confidence)}</span>
        </article>
      ))}
    </div>
  )
}

function AlertTable({ alerts }: { alerts: AlertEntry[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Prediction</th>
            <th>Severity</th>
            <th>Confidence</th>
            <th>Anomaly</th>
            <th>Top SHAP</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => (
            <tr key={`${alert.timestamp}-${alert.prediction}`}>
              <td>{formatDate(alert.timestamp)}</td>
              <td>{alert.prediction}</td>
              <td>
                <SeverityBadge severity={alert.severity} />
              </td>
              <td>{formatPercent(alert.confidence)}</td>
              <td>{formatNumber(alert.anomaly_score)}</td>
              <td>{formatTopFeature(alert.shap_top_features)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SimulationTable({
  simulations,
}: {
  simulations: SimulateResponse[]
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Window</th>
            <th>Risk</th>
            <th>Attacks</th>
            <th>Anomalies</th>
            <th>Severity</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {simulations.map((simulation) => (
            <tr key={`${simulation.timestamp}-${simulation.window_size}`}>
              <td>{formatDate(simulation.timestamp)}</td>
              <td>{simulation.window_size}</td>
              <td>{formatNumber(simulation.mean_risk_score)}</td>
              <td>{simulation.attack_count}</td>
              <td>{simulation.anomaly_count}</td>
              <td>
                <SeverityBadge severity={simulation.severity} />
              </td>
              <td>{simulation.alert_triggered ? 'Alert' : 'Clear'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TopFeatures({ features }: { features: ShapFeature[] }) {
  if (!features.length) {
    return <EmptyState text="No SHAP features returned." />
  }

  return (
    <div className="feature-list">
      <h3>Top SHAP features</h3>
      {features.map((feature) => (
        <div className="feature-row" key={feature.feature}>
          <span>{feature.feature}</span>
          <strong>{formatNumber(feature.impact)}</strong>
        </div>
      ))}
    </div>
  )
}

function ConfusionMatrix({ matrix }: { matrix: number[][] }) {
  return (
    <div className="matrix-block">
      <h3>Confusion matrix</h3>
      <div className="matrix-grid">
        {matrix.flatMap((row, rowIndex) =>
          row.map((value, columnIndex) => (
            <div className="matrix-cell" key={`${rowIndex}-${columnIndex}`}>
              <span>
                {rowIndex === 0 && columnIndex === 0 && 'TN'}
                {rowIndex === 0 && columnIndex === 1 && 'FP'}
                {rowIndex === 1 && columnIndex === 0 && 'FN'}
                {rowIndex === 1 && columnIndex === 1 && 'TP'}
              </span>
              <strong>{value}</strong>
            </div>
          )),
        )}
      </div>
    </div>
  )
}

function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`severity-badge severity-${severity.toLowerCase()}`}>
      {severity}
    </span>
  )
}

function EmptyState({ text }: { text: string }) {
  return <p className="empty-state">{text}</p>
}

function parseFeatureJson(featureJson: string): ParsedFeatures {
  let parsed: unknown

  try {
    parsed = JSON.parse(featureJson)
  } catch {
    return { ok: false, error: 'Feature input must be valid JSON.' }
  }

  if (!isPlainObject(parsed)) {
    return { ok: false, error: 'Feature input must be a JSON object.' }
  }

  const features: Record<string, number> = {}

  for (const [key, value] of Object.entries(parsed)) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      return {
        ok: false,
        error: `Feature "${key}" must be a finite number.`,
      }
    }

    features[key] = value
  }

  if (!Object.keys(features).length) {
    return { ok: false, error: 'Feature input must include at least one field.' }
  }

  return { ok: true, value: features }
}

function validateThreshold(value: string) {
  const parsed = Number(value)

  if (value.trim() === '' || !Number.isFinite(parsed)) {
    return 'Threshold must be a number from 0 to 1.'
  }

  if (parsed < 0 || parsed > 1) {
    return 'Threshold must be between 0 and 1.'
  }

  return ''
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function uniqueOptions(values: string[]) {
  return Array.from(new Set(values)).sort()
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function formatNumber(value: number) {
  return value.toFixed(3)
}

function formatDate(value: string) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString()
}

function formatTopFeature(features: ShapFeature[]) {
  const [topFeature] = features
  return topFeature
    ? `${topFeature.feature} (${formatNumber(topFeature.impact)})`
    : 'None'
}

function errorMessage(error: unknown) {
  if (!error) {
    return ''
  }

  if (error instanceof Error) {
    return error.message
  }

  return 'Request failed.'
}

export default App
