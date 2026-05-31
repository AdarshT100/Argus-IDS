export const chartColors = {
  green: '#12b76a',
  amber: '#f79009',
  red: '#f04438',
  teal: '#0f766e',
  gray: '#667085',
}

export const severityOrder = ['LOW', 'MEDIUM', 'HIGH', 'ANOMALY']
export const chartMargin = { top: 8, right: 20, bottom: 8, left: 8 }

export function severityColor(severity: string): string {
  const normalized = severity.toUpperCase()

  if (normalized === 'LOW') {
    return chartColors.green
  }

  if (normalized === 'MEDIUM') {
    return chartColors.amber
  }

  if (normalized === 'HIGH' || normalized === 'ANOMALY') {
    return chartColors.red
  }

  return chartColors.gray
}
