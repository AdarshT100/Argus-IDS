import { useState, type SubmitEvent } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Alert } from '../components/ui/alert'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { MetricCard, Panel, QueryState } from '../components/shared'
import { chartColors, chartMargin } from '../lib/constants'
import { useThresholdMetricsQuery } from '../lib/queries'
import {
  errorMessage,
  formatPercent,
  formatPercentTick,
  formatTooltipPercent,
} from '../lib/utils'

export default function MetricsPage() {
  const [thresholdInput, setThresholdInput] = useState('0.5')
  const [threshold, setThreshold] = useState(0.5)
  const thresholdValidation = validateThreshold(thresholdInput)
  const metricsQuery = useThresholdMetricsQuery(threshold)

  function submitThreshold(event: SubmitEvent<HTMLFormElement>) {
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
          <Button type="submit">Load metrics</Button>
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
