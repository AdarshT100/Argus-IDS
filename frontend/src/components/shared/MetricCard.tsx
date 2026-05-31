type MetricCardProps = {
  label: string
  value: string
  detail: string
}

export function MetricCard({ label, value, detail }: MetricCardProps) {
  return (
    <article className="metric-card">
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  )
}
