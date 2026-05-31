import { useState, type SubmitEvent } from 'react'
import { Alert } from '../components/ui/alert'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import {
  Panel,
  QueryState,
  SeverityBadge,
  SimulationRiskChart,
} from '../components/shared'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrap,
} from '../components/ui/table'
import { useSimulationMutation, useSimulationsQuery } from '../lib/queries'
import type { SimulateResponse } from '../lib/types'
import { errorMessage, formatDate, formatNumber } from '../lib/utils'

export default function SimulationsPage() {
  const [windowSize, setWindowSize] = useState('50')
  const [validationError, setValidationError] = useState('')
  const simulationsQuery = useSimulationsQuery()
  const simulationMutation = useSimulationMutation()
  const simulations = simulationsQuery.data?.simulations ?? []

  function submitSimulation(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const parsedWindowSize = Number(windowSize)

    if (
      !Number.isInteger(parsedWindowSize) ||
      parsedWindowSize < 25 ||
      parsedWindowSize > 100
    ) {
      setValidationError('Window size must be a whole number from 25 to 100.')
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
            min="25"
            max="100"
            step="1"
            type="number"
            value={windowSize}
            onChange={(event) => setWindowSize(event.target.value)}
          />
          {activeError && <Alert variant="error">{activeError}</Alert>}
          <Button disabled={simulationMutation.isPending} type="submit">
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
