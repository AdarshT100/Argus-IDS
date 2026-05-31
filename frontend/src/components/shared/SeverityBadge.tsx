import { Badge } from '../ui/badge'
import type { Severity } from '../../lib/types'

type SeverityBadgeProps = {
  severity: Severity
}

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  return <Badge variant={severityVariant(severity)}>{severity}</Badge>
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
