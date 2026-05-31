import type { ShapFeature } from './types'

export type ExplanationLine = {
  key: string
  kind: 'body' | 'bullet' | 'heading' | 'spacer'
  text: string
}

export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ')
}

export function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

export function formatPercentTick(value: number) {
  return `${Math.round(value * 100)}%`
}

export function formatNumber(value: number) {
  return value.toFixed(3)
}

export function formatReadableFeatureValue(value: number) {
  const absoluteValue = Math.abs(value)

  if (value === 0) {
    return '0'
  }

  if (absoluteValue < 0.000001) {
    return value < 0 ? '< -0.000001' : '< 0.000001'
  }

  const maximumFractionDigits = absoluteValue >= 100 ? 0 : 6

  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits,
  }).format(value)
}

export function formatExplanationText(text: string): ExplanationLine[] {
  return text.split('\n').map((line, index) => {
    const trimmedLine = line.trim()
    const key = `${index}-${trimmedLine}`

    if (!trimmedLine) {
      return { key, kind: 'spacer', text: '' }
    }

    const headingMatch = trimmedLine.match(/^\*\*(.+):\*\*$/)

    if (headingMatch) {
      return {
        key,
        kind: 'heading',
        text: headingMatch[1],
      }
    }

    const isBullet = trimmedLine.startsWith('•')
    const normalizedLine = trimmedLine
      .replace(/^•\s*/, '')
      .replace(
        /(=\s*)([-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)/gi,
        (_match, prefix: string, rawValue: string) =>
          `${prefix}${formatReadableFeatureValue(Number(rawValue))}`,
      )

    return {
      key,
      kind: isBullet ? 'bullet' : 'body',
      text: normalizedLine,
    }
  })
}

export function formatCompactNumber(value: number) {
  return Number.isInteger(value) ? value.toString() : value.toFixed(2)
}

export function formatTooltipNumber(value: unknown) {
  return typeof value === 'number' ? formatNumber(value) : String(value)
}

export function formatSimulationTooltip(value: unknown, name: unknown) {
  if (name === 'Mean risk' && typeof value === 'number') {
    return formatPercent(value)
  }

  return formatTooltipNumber(value)
}

export function formatTooltipPercent(value: unknown) {
  return typeof value === 'number' ? formatPercent(value) : String(value)
}

export function formatDate(value: string) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString()
}

export function shortDate(value: string) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatTopFeature(features: ShapFeature[]) {
  const [topFeature] = features
  return topFeature
    ? `${topFeature.feature} (${formatNumber(topFeature.impact)})`
    : 'None'
}

export function errorMessage(error: unknown) {
  if (!error) {
    return ''
  }

  if (error instanceof Error) {
    return error.message
  }

  return 'Request failed.'
}

export function uniqueOptions(values: string[]) {
  return Array.from(new Set(values)).sort()
}

export function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
