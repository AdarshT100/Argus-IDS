import type { SimulateResponse } from '../../lib/types'
import { formatDate, formatNumber } from '../../lib/utils'
import { SeverityBadge } from './SeverityBadge'

type SimulationDetailsProps = {
  simulation: SimulateResponse
}

export function SimulationDetails({ simulation }: SimulationDetailsProps) {
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
