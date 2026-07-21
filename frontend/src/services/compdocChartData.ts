import type { ChartData } from 'chart.js'
import type { DashboardPoint, DashboardTimeline } from '@/models/compdocDashboard'

export const STATUS_PRESENTATION = [
  { value: 'to_be_issued', label: 'To be Issued', color: '#f59e0b' },
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

/** Build stable status rows while preserving zero-value categories in the legend. */
export function createStatusChartRows(counts: Record<string, number>): StatusChartRow[] {
  const total = Object.values(counts).reduce((sum, value) => sum + safeNumber(value), 0)
  return STATUS_PRESENTATION.map((status) => {
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

/** Build stepped burndown series with a visual start anchor. */
export function createTimelineChartData(
  timeline: DashboardTimeline,
  total: number
): ChartData<'line'> {
  return {
    datasets: [
      timelineDataset('Scheduled', timeline.scheduled, total, '#64748b', [7, 5], false),
      timelineDataset('Actual', timeline.actual, total, '#2563eb', undefined, true)
    ]
  }
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
  points: DashboardPoint[],
  total: number,
  color: string,
  borderDash: number[] | undefined,
  fill: boolean
) {
  return {
    label,
    data: withStartAnchor(points, total),
    borderColor: color,
    backgroundColor: fill ? 'rgba(37, 99, 235, 0.12)' : 'transparent',
    borderWidth: label === 'Actual' ? 3 : 2,
    borderDash,
    stepped: 'after' as const,
    tension: 0,
    pointRadius: points.length <= 12 ? 3 : 0,
    pointHoverRadius: 6,
    pointHitRadius: 12,
    fill
  }
}

function withStartAnchor(points: DashboardPoint[], total: number) {
  const normalized = points.flatMap(normalizePoint).sort((left, right) => left.x - right.x)
  if (!normalized.length || normalized[0].y >= total) return normalized
  const firstDate = new Date(normalized[0].x)
  firstDate.setDate(firstDate.getDate() - 1)
  return [{ x: firstDate.getTime(), y: total }, ...normalized]
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
