import {
  AlertSeverityChart,
  MetricCard,
  Panel,
  QueryState,
  SeverityBadge,
  SimulationRiskChart,
} from '../components/shared'
import { useAlertsQuery, useHealthQuery, useSimulationsQuery } from '../lib/queries'
import type { AlertEntry, SimulateResponse } from '../lib/types'
import { errorMessage, formatDate, formatNumber, formatPercent } from '../lib/utils'

export default function DashboardPage() {
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
