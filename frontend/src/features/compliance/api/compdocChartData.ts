import type { CompdocOption } from './compdocCatalog'
import type { ChartData } from 'chart.js'
import type {
  DashboardPoint,
  DashboardTimeline
} from '@/features/compliance/models/compdocDashboard'

export const STATUS_PRESENTATION = [
  { value: 'to_be_issued', label: 'To be Issued', color: '#f59e0b' },
  { value: 'expected', label: 'Expected', color: '#f59e0b' },
  { value: 'missing_target', label: 'Target date missing', color: '#94a3b8' },
  { value: 'delayed', label: 'Delayed', color: '#ef4444' },
  { value: 'to_be_updated', label: 'To be Updated', color: '#06b6d4' },
  { value: 'airworthiness_review', label: 'Airworthiness Review', color: '#8b5cf6' },
  { value: 'to_be_re-submitted', label: 'To be Re-Submitted', color: '#f97316' },
  { value: 'authority_review', label: 'Authority Review', color: '#3b82f6' },
  { value: 'authority_approved', label: 'Authority Approved', color: '#22c55e' },
  { value: 'unknown', label: 'Unknown', color: '#94a3b8' }
] as const

export interface StatusChartRow {
  value: string
  label: string
  color: string
  count: number
  percentage: number
}

/** Preserve every CAT value, including missing CAT, with stable category ordering. */
export function createCatChartRows(
  counts: Record<string, number>,
  colors: string[],
  neutralColor: string
): StatusChartRow[] {
  const total = Object.values(counts).reduce((sum, count) => sum + safeNumber(count), 0)
  return Object.keys(counts)
    .sort((left, right) => {
      if (!left) return 1
      if (!right) return -1
      return left.localeCompare(right, 'en', { numeric: true })
    })
    .map((value, index) => {
      const count = safeNumber(counts[value])
      return {
        value,
        label: value || 'Unspecified',
        color: value ? colors[index % colors.length] || neutralColor : neutralColor,
        count,
        percentage: total ? Math.round((count / total) * 100) : 0
      }
    })
}

/** Build stable status rows while preserving zero-value categories in the legend. */
export function createStatusChartRows(
  counts: Record<string, number>,
  options: CompdocOption[] = [],
  neutralColor = 'currentColor'
): StatusChartRow[] {
  const total = Object.values(counts).reduce((sum, value) => sum + safeNumber(value), 0)
  const vocabulary = new Map(options.map((option) => [option.value, option.label]))
  Object.keys(counts).forEach((value) => {
    if (!vocabulary.has(value))
      vocabulary.set(
        value,
        STATUS_PRESENTATION.find((item) => item.value === value)?.label ||
          value.replaceAll('_', ' ')
      )
  })
  return [...vocabulary].map(([value, label]) => {
    const color = STATUS_PRESENTATION.find((item) => item.value === value)?.color || neutralColor
    const status = { value, label, color }
    const count = safeNumber(counts[status.value])
    return { ...status, count, percentage: total ? Math.round((count / total) * 100) : 0 }
  })
}

/** Return a zero-safe doughnut dataset without invisible zero-sized arcs. */
export function createStatusChartData(rows: StatusChartRow[]): ChartData<'doughnut'> {
  const visible = rows.filter((row) => row.count > 0)
  return {
    labels: visible.map((row) => row.label),
    datasets: [
      {
        label: 'Documents',
        data: visible.map((row) => row.count),
        backgroundColor: visible.map((row) => row.color),
        borderWidth: 3,
        hoverOffset: 10,
        spacing: 2
      }
    ]
  }
}

/** Align all series to calendar days so tooltips compare the same date. */
export function createTimelineChartData(
  timeline: DashboardTimeline,
  total: number,
  colors = { scheduled: '#64748b', actual: '#2563eb', revised: '#8b5cf6' }
): ChartData<'line'> {
  const source = [timeline.scheduled, timeline.actual]
  if (timeline.revised_scheduled?.length) source.push(timeline.revised_scheduled)
  const series = dailySeries(source, timeline.today, total)
  const datasets = [
    timelineDataset('Scheduled', series[0], colors.scheduled, [7, 5]),
    timelineDataset('Actual', series[1], colors.actual)
  ]
  if (series[2])
    datasets.push(timelineDataset('Revised scheduled', series[2], colors.revised, [2, 4]))
  return { datasets }
}

/** Build the three unchanged pending-day categories as a horizontal bar dataset. */
export function createPendingChartData(
  pendingDays: Record<'authority' | 'ubm' | 'aw', number>
): ChartData<'bar'> {
  return {
    labels: ['Authority', 'UBM', 'Airworthiness'],
    datasets: [
      {
        label: 'Accumulated days',
        data: [pendingDays.authority, pendingDays.ubm, pendingDays.aw].map(safeNumber),
        backgroundColor: ['#3b82f6', '#06b6d4', '#8b5cf6'],
        borderRadius: 8,
        borderSkipped: false,
        barPercentage: 0.62
      }
    ]
  }
}

function timelineDataset(
  label: string,
  points: Array<{ x: number; y: number }>,
  color: string,
  borderDash?: number[]
) {
  return {
    label,
    data: points,
    borderColor: color,
    backgroundColor: color,
    borderWidth: label === 'Actual' ? 3 : 2,
    borderDash,
    // Hold the earlier value until the next event's x coordinate.
    stepped: 'before' as const,
    tension: 0,
    pointRadius: 0,
    pointHoverRadius: 5,
    pointHitRadius: 12,
    fill: false
  }
}

function dailySeries(source: DashboardPoint[][], today: DashboardPoint[], total: number) {
  const normalized = source.map((points) =>
    points.flatMap(normalizePoint).sort((a, b) => a.x - b.x)
  )
  const dates = [
    ...normalized.flat().map((point) => point.x),
    ...today.flatMap(normalizePoint).map((point) => point.x)
  ]
  if (!dates.length) return source.map(() => [])
  const start = new Date(Math.min(...dates))
  start.setDate(start.getDate() - 1)
  const end = Math.max(...dates)
  return normalized.map((points) => {
    const daily: Array<{ x: number; y: number }> = []
    let index = 0
    let remaining = total
    // Calendar increments preserve local midnights across daylight-saving changes.
    for (const day = new Date(start); day.getTime() <= end; day.setDate(day.getDate() + 1)) {
      while (index < points.length && points[index].x <= day.getTime()) {
        remaining = points[index++].y
      }
      daily.push({ x: day.getTime(), y: remaining })
    }
    return daily
  })
}

function normalizePoint(point: DashboardPoint) {
  const x = toIsoDate(point.x)
  return x ? [{ x: new Date(`${x}T00:00:00`).getTime(), y: Math.max(0, safeNumber(point.y)) }] : []
}

export function toIsoDate(value: string) {
  const eu = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value)
  if (eu) return `${eu[3]}-${eu[2]}-${eu[1]}`
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null
}

function safeNumber(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) && number > 0 ? number : 0
}
