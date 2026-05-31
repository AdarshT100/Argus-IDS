import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import { severityColor, severityOrder } from '../../lib/constants'
import { uniqueOptions } from '../../lib/utils'
import type { AlertEntry } from '../../lib/types'

type AlertSeverityChartProps = {
  alerts: AlertEntry[]
}

export function AlertSeverityChart({ alerts }: AlertSeverityChartProps) {
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
