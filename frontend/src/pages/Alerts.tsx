import { useState } from 'react'
import {
  AlertSeverityChart,
  Panel,
  QueryState,
  SeverityBadge,
} from '../components/shared'
import { Select } from '../components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrap,
} from '../components/ui/table'
import { useAlertsQuery } from '../lib/queries'
import type { AlertEntry } from '../lib/types'
import {
  formatDate,
  formatNumber,
  formatPercent,
  formatTopFeature,
  uniqueOptions,
} from '../lib/utils'

export default function AlertsPage() {
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
