import { useMemo, useState, type FormEvent, type ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import './App.css'
import { Alert } from './components/ui/alert'
import { Badge } from './components/ui/badge'
import { Button } from './components/ui/button'
import { Input } from './components/ui/input'
import { Select } from './components/ui/select'
import { Skeleton } from './components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrap,
} from './components/ui/table'
import { Textarea } from './components/ui/textarea'
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

      <section className="content-grid two-column">
        <Panel title="Alert severity mix" eyebrow="Severity distribution">
          <QueryState
            isLoading={alertsQuery.isLoading}
            error={alertsQuery.error}
            empty={!alerts.length}
            emptyText="No alerts available for severity charting."
          >
            <AlertSeverityChart alerts={alerts} />
          </QueryState>
        </Panel>

        <Panel title="Simulation risk trend" eyebrow="Recent windows">
          <QueryState
            isLoading={simulationsQuery.isLoading}
            error={simulationsQuery.error}
            empty={!simulations.length}
            emptyText="No simulations available for risk charting."
          >
            <SimulationRiskChart simulations={simulations} />
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
          <Textarea
            aria-label="Feature JSON"
            className="json-input"
            value={featureJson}
            onChange={(event) => setFeatureJson(event.target.value)}
            spellCheck={false}
          />
          {activeError && <Alert variant="error">{activeError}</Alert>}
          <div className="button-row">
            <Button
              disabled={predictMutation.isPending}
              type="submit"
            >
              {predictMutation.isPending ? 'Predicting...' : 'Run prediction'}
            </Button>
            <Button
              disabled={randomMutation.isPending}
              variant="secondary"
              onClick={runRandomPrediction}
            >
              {randomMutation.isPending ? 'Sampling...' : 'Random sample'}
            </Button>
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
          <Input
            id="window-size"
            min="1"
            step="1"
            type="number"
            value={windowSize}
            onChange={(event) => setWindowSize(event.target.value)}
          />
          {activeError && <Alert variant="error">{activeError}</Alert>}
          <Button
            disabled={simulationMutation.isPending}
            type="submit"
          >
            {simulationMutation.isPending ? 'Running...' : 'Run simulation'}
          </Button>
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
          <div className="metrics-stack">
            <SimulationRiskChart simulations={simulations} />
            <SimulationTable simulations={simulations} />
          </div>
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
    <section className="content-grid">
      <Panel title="Alert severity" eyebrow="Filtered distribution">
        <QueryState
          isLoading={alertsQuery.isLoading}
          error={alertsQuery.error}
          empty={!filteredAlerts.length}
          emptyText="No alerts match the current filters."
        >
          <AlertSeverityChart alerts={filteredAlerts} />
        </QueryState>
      </Panel>

      <Panel title="Recent alerts" eyebrow="Local filters">
      <div className="filter-row">
        <label>
          Severity
          <Select
            value={severityFilter}
            onChange={(event) => setSeverityFilter(event.target.value)}
          >
            <option value="ALL">All severities</option>
            {severities.map((severity) => (
              <option key={severity} value={severity}>
                {severity}
              </option>
            ))}
          </Select>
        </label>
        <label>
          Prediction
          <Select
            value={predictionFilter}
            onChange={(event) => setPredictionFilter(event.target.value)}
          >
            <option value="ALL">All predictions</option>
            {predictions.map((prediction) => (
              <option key={prediction} value={prediction}>
                {prediction}
              </option>
            ))}
          </Select>
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
    </section>
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
          <Input
            id="threshold"
            max="1"
            min="0"
            step="0.01"
            type="number"
            value={thresholdInput}
            onChange={(event) => setThresholdInput(event.target.value)}
          />
          {thresholdValidation && (
            <Alert variant="error">{thresholdValidation}</Alert>
          )}
          {metricsQuery.error && (
            <Alert variant="error">{errorMessage(metricsQuery.error)}</Alert>
          )}
          <Button type="submit">
            Load metrics
          </Button>
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
              <ThresholdMetricsChart
                precision={metrics.precision}
                recall={metrics.recall}
                f1Score={metrics.f1_score}
              />
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
      <div className="panel-header">
        <span className="panel-accent" aria-hidden="true" />
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="panel-body">{children}</div>
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
    return <LoadingState />
  }

  if (error) {
    return <Alert variant="error">{errorMessage(error)}</Alert>
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
      <ExplanationText text={result.explanation_text} />
      <TopFeatures features={result.shap_top_features} />
    </div>
  )
}

function ExplanationText({ text }: { text: string }) {
  if (!text.trim()) {
    return <EmptyState text="No SHAP explanation returned." />
  }

  return (
    <section className="explanation-block">
      <h3>Why this result</h3>
      <p>{text}</p>
    </section>
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
    <TableWrap>
      <Table>
        <TableHead>
          <TableRow>
            <TableHeader>Time</TableHeader>
            <TableHeader>Prediction</TableHeader>
            <TableHeader>Severity</TableHeader>
            <TableHeader>Confidence</TableHeader>
            <TableHeader>Anomaly</TableHeader>
            <TableHeader>Top SHAP</TableHeader>
          </TableRow>
        </TableHead>
        <TableBody>
          {alerts.map((alert) => (
            <TableRow key={`${alert.timestamp}-${alert.prediction}`}>
              <TableCell>{formatDate(alert.timestamp)}</TableCell>
              <TableCell>{alert.prediction}</TableCell>
              <TableCell>
                <SeverityBadge severity={alert.severity} />
              </TableCell>
              <TableCell>{formatPercent(alert.confidence)}</TableCell>
              <TableCell>{formatNumber(alert.anomaly_score)}</TableCell>
              <TableCell>{formatTopFeature(alert.shap_top_features)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableWrap>
  )
}

function SimulationTable({
  simulations,
}: {
  simulations: SimulateResponse[]
}) {
  return (
    <TableWrap>
      <Table>
        <TableHead>
          <TableRow>
            <TableHeader>Time</TableHeader>
            <TableHeader>Window</TableHeader>
            <TableHeader>Risk</TableHeader>
            <TableHeader>Attacks</TableHeader>
            <TableHeader>Anomalies</TableHeader>
            <TableHeader>Severity</TableHeader>
            <TableHeader>Status</TableHeader>
          </TableRow>
        </TableHead>
        <TableBody>
          {simulations.map((simulation) => (
            <TableRow key={`${simulation.timestamp}-${simulation.window_size}`}>
              <TableCell>{formatDate(simulation.timestamp)}</TableCell>
              <TableCell>{simulation.window_size}</TableCell>
              <TableCell>{formatNumber(simulation.mean_risk_score)}</TableCell>
              <TableCell>{simulation.attack_count}</TableCell>
              <TableCell>{simulation.anomaly_count}</TableCell>
              <TableCell>
                <SeverityBadge severity={simulation.severity} />
              </TableCell>
              <TableCell>{simulation.alert_triggered ? 'Alert' : 'Clear'}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableWrap>
  )
}

function TopFeatures({ features }: { features: ShapFeature[] }) {
  if (!features.length) {
    return <EmptyState text="No SHAP features returned." />
  }

  return (
    <div className="feature-list">
      <h3>Top SHAP features</h3>
      <ShapImpactChart features={features} />
      {features.map((feature) => (
        <div className="feature-row" key={feature.feature}>
          <span>{feature.feature}</span>
          <strong>{formatNumber(feature.impact)}</strong>
        </div>
      ))}
    </div>
  )
}

function ShapImpactChart({ features }: { features: ShapFeature[] }) {
  const data = features
    .map((feature) => ({
      feature: feature.feature,
      impact: feature.impact,
      absoluteImpact: Math.abs(feature.impact),
    }))
    .sort((left, right) => right.absoluteImpact - left.absoluteImpact)

  return (
    <div className="chart-box tall-chart">
      <ResponsiveContainer height="100%" width="100%">
        <BarChart data={data} layout="vertical" margin={chartMargin}>
          <CartesianGrid horizontal={false} stroke="#e4e7ec" />
          <XAxis tickFormatter={formatCompactNumber} type="number" />
          <YAxis
            dataKey="feature"
            tick={{ fontSize: 12 }}
            type="category"
            width={120}
          />
          <Tooltip formatter={(value) => formatTooltipNumber(value)} />
          <Bar dataKey="impact" name="SHAP impact" radius={[0, 4, 4, 0]}>
            {data.map((item) => (
              <Cell
                fill={item.impact >= 0 ? chartColors.teal : chartColors.red}
                key={item.feature}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function AlertSeverityChart({ alerts }: { alerts: AlertEntry[] }) {
  const data = severityOrder
    .map((severity) => ({
      severity,
      count: alerts.filter((alert) => alert.severity === severity).length,
    }))
    .filter((item) => item.count > 0)

  const customSeverities = uniqueOptions(
    alerts
      .map((alert) => alert.severity)
      .filter((severity) => !severityOrder.includes(severity)),
  ).map((severity) => ({
    severity,
    count: alerts.filter((alert) => alert.severity === severity).length,
  }))

  return (
    <div className="chart-box split-chart">
      <ResponsiveContainer height="100%" width="100%">
        <PieChart>
          <Pie
            data={[...data, ...customSeverities]}
            dataKey="count"
            innerRadius={48}
            nameKey="severity"
            outerRadius={78}
            paddingAngle={2}
          >
            {[...data, ...customSeverities].map((item) => (
              <Cell fill={severityColor(item.severity)} key={item.severity} />
            ))}
          </Pie>
          <Tooltip formatter={(value) => `${value} alerts`} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

function SimulationRiskChart({
  simulations,
}: {
  simulations: SimulateResponse[]
}) {
  const data = [...simulations]
    .reverse()
    .slice(-12)
    .map((simulation) => ({
      time: shortDate(simulation.timestamp),
      risk: simulation.mean_risk_score,
      attacks: simulation.attack_count,
      anomalies: simulation.anomaly_count,
    }))

  return (
    <div className="chart-box">
      <ResponsiveContainer height="100%" width="100%">
        <LineChart data={data} margin={chartMargin}>
          <CartesianGrid stroke="#e4e7ec" />
          <XAxis dataKey="time" tick={{ fontSize: 12 }} />
          <YAxis tickFormatter={formatCompactNumber} />
          <Tooltip formatter={(value) => formatTooltipNumber(value)} />
          <Legend />
          <Line
            dataKey="risk"
            name="Mean risk"
            stroke={chartColors.teal}
            strokeWidth={2}
            type="monotone"
          />
          <Line
            dataKey="attacks"
            name="Attacks"
            stroke={chartColors.red}
            strokeWidth={2}
            type="monotone"
          />
          <Line
            dataKey="anomalies"
            name="Anomalies"
            stroke={chartColors.amber}
            strokeWidth={2}
            type="monotone"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function ThresholdMetricsChart({
  precision,
  recall,
  f1Score,
}: {
  precision: number
  recall: number
  f1Score: number
}) {
  const data = [
    { metric: 'Precision', value: precision },
    { metric: 'Recall', value: recall },
    { metric: 'F1 score', value: f1Score },
  ]

  return (
    <div className="chart-block">
      <h3>Metric balance</h3>
      <div className="chart-box compact-chart">
        <ResponsiveContainer height="100%" width="100%">
          <BarChart data={data} margin={chartMargin}>
            <CartesianGrid vertical={false} stroke="#e4e7ec" />
            <XAxis dataKey="metric" tick={{ fontSize: 12 }} />
            <YAxis domain={[0, 1]} tickFormatter={formatPercentTick} />
            <Tooltip formatter={(value) => formatTooltipPercent(value)} />
            <Bar dataKey="value" fill={chartColors.teal} name="Score" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
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
  return <Badge variant={severityVariant(severity)}>{severity}</Badge>
}

function EmptyState({ text }: { text: string }) {
  return <Alert>{text}</Alert>
}

function LoadingState() {
  return (
    <div className="loading-stack" aria-label="Loading backend data">
      <Skeleton />
      <Skeleton className="short" />
      <Skeleton className="medium" />
    </div>
  )
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

const chartColors = {
  green: '#12b76a',
  amber: '#f79009',
  red: '#f04438',
  teal: '#0f766e',
  gray: '#667085',
}

const severityOrder = ['LOW', 'MEDIUM', 'HIGH', 'ANOMALY']
const chartMargin = { top: 8, right: 20, bottom: 8, left: 8 }

function severityColor(severity: string) {
  const normalized = severity.toUpperCase()

  if (normalized === 'LOW') {
    return chartColors.green
  }

  if (normalized === 'MEDIUM') {
    return chartColors.amber
  }

  if (normalized === 'HIGH' || normalized === 'ANOMALY') {
    return chartColors.red
  }

  return chartColors.gray
}

function severityVariant(severity: string) {
  const normalized = severity.toUpperCase()

  if (normalized === 'LOW') {
    return 'success'
  }

  if (normalized === 'MEDIUM') {
    return 'warning'
  }

  if (normalized === 'HIGH' || normalized === 'ANOMALY') {
    return 'danger'
  }

  return 'neutral'
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function formatPercentTick(value: number) {
  return `${Math.round(value * 100)}%`
}

function formatNumber(value: number) {
  return value.toFixed(3)
}

function formatCompactNumber(value: number) {
  return Number.isInteger(value) ? value.toString() : value.toFixed(2)
}

function formatTooltipNumber(value: unknown) {
  return typeof value === 'number' ? formatNumber(value) : String(value)
}

function formatTooltipPercent(value: unknown) {
  return typeof value === 'number' ? formatPercent(value) : String(value)
}

function formatDate(value: string) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString()
}

function shortDate(value: string) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
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
