import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { chartColors, chartMargin } from '../../lib/constants'
import {
  formatCompactNumber,
  formatPercentTick,
  formatSimulationTooltip,
  shortDate,
} from '../../lib/utils'
import type { SimulateResponse } from '../../lib/types'

type SimulationRiskChartProps = {
  simulations: SimulateResponse[]
}

export function SimulationRiskChart({ simulations }: SimulationRiskChartProps) {
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
        <LineChart data={data} margin={{ ...chartMargin, right: 34 }}>
          <CartesianGrid stroke="#e4e7ec" />
          <XAxis dataKey="time" tick={{ fontSize: 12 }} />
          <YAxis
            allowDecimals={false}
            tickFormatter={formatCompactNumber}
            yAxisId="count"
          />
          <YAxis
            domain={[0, 1]}
            orientation="right"
            tickFormatter={formatPercentTick}
            yAxisId="risk"
          />
          <Tooltip formatter={formatSimulationTooltip} />
          <Legend />
          <Line
            dataKey="risk"
            name="Mean risk"
            stroke={chartColors.teal}
            strokeWidth={2}
            type="monotone"
            yAxisId="risk"
          />
          <Line
            dataKey="attacks"
            name="Attacks"
            stroke={chartColors.red}
            strokeWidth={2}
            type="monotone"
            yAxisId="count"
          />
          <Line
            dataKey="anomalies"
            name="Anomalies"
            stroke={chartColors.amber}
            strokeWidth={2}
            type="monotone"
            yAxisId="count"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
