import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { chartColors, chartMargin } from '../../lib/constants'
import { formatCompactNumber, formatTooltipNumber } from '../../lib/utils'
import type { ShapFeature } from '../../lib/types'

type ShapImpactChartProps = {
  features: ShapFeature[]
}

export function ShapImpactChart({ features }: ShapImpactChartProps) {
  const data = features
    .map((feature) => ({
      feature: feature.feature,
      impact: feature.impact,
      absoluteImpact: Math.abs(feature.impact),
    }))
    .sort((left, right) => right.absoluteImpact - left.absoluteImpact)

  return (
    <div className="chart-box shap-chart">
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
