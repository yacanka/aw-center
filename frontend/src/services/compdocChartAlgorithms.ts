import type { ICompDoc, IStatusFlow } from '@/models/compdocs'
import type { DashboardPoint, DashboardTimeline } from '@/models/compdocDashboard'

const STATUS_BUCKETS = new Set([
  'to_be_issued',
  'airworthiness_review',
  'to_be_re-submitted',
  'to_be_updated',
  'authority_review',
  'authority_approved',
  'delayed',
  'unknown'
])
const PENDING_BUCKETS: Record<string, 'authority' | 'ubm' | 'aw'> = {
  to_be_updated: 'ubm',
  airworthiness_review: 'aw',
  'to_be_re-submitted': 'aw',
  authority_review: 'authority'
}

export interface ClientCompdocSummary {
  statuses: Record<string, number>
  pendingDays: Record<'authority' | 'ubm' | 'aw', number>
  timeline: DashboardTimeline
}

/** Aggregate visible CompDocs with the same buckets used by the project dashboard. */
export function buildClientCompdocSummary(
  rows: ICompDoc[],
  today = new Date()
): ClientCompdocSummary {
  const statuses = emptyStatuses()
  const pendingDays = { authority: 0, ubm: 0, aw: 0 }
  const scheduled = new Map<number, number>()
  const actual = new Map<number, number>()
  rows.forEach((row) => {
    statuses[normalizedStatus(row.status)] += 1
    const entries = normalizedFlow(row.status_flow)
    accumulatePending(entries, pendingDays, startOfDay(today))
    accumulateDate(scheduled, entries[0], new Set(['to_be_issued', 'delayed']))
    accumulateDate(actual, entries[1])
  })
  return {
    statuses,
    pendingDays,
    timeline: buildTimeline(scheduled, actual, rows.length, startOfDay(today))
  }
}

function emptyStatuses() {
  return Object.fromEntries([...STATUS_BUCKETS].map((status) => [status, 0]))
}

function normalizedStatus(value: unknown) {
  const status = String(value || 'unknown')
  return STATUS_BUCKETS.has(status) ? status : 'unknown'
}

function normalizedFlow(value: IStatusFlow[]) {
  if (!Array.isArray(value)) return []
  return value.flatMap((entry) => {
    const date = parseDate(entry?.date)
    return entry?.status && date ? [{ status: entry.status, date }] : []
  })
}

function accumulatePending(
  entries: Array<{ status: string; date: Date }>,
  totals: Record<'authority' | 'ubm' | 'aw', number>,
  today: Date
) {
  entries.forEach((entry, index) => {
    const endedAt = entries[index + 1]?.date || today
    const elapsed = dayDifference(endedAt, entry.date)
    if (elapsed < 0) return
    const bucket = PENDING_BUCKETS[entry.status]
    if (bucket) totals[bucket] += elapsed
    else if (entry.status === 'to_be_issued' && index === entries.length - 1) totals.ubm += elapsed
  })
}

function accumulateDate(
  counter: Map<number, number>,
  entry?: { status: string; date: Date },
  acceptedStatuses?: Set<string>
) {
  if (!entry || (acceptedStatuses && !acceptedStatuses.has(entry.status))) return
  const timestamp = entry.date.getTime()
  counter.set(timestamp, (counter.get(timestamp) || 0) + 1)
}

function buildTimeline(
  scheduled: Map<number, number>,
  actual: Map<number, number>,
  total: number,
  today: Date
): DashboardTimeline {
  const scheduledPoints = remainingSeries(scheduled, total)
  const actualPoints = remainingSeries(actual, total)
  const todayPoint = { x: formatDate(today), y: remainingOn(actual, total, today.getTime()) }
  return {
    scheduled: scheduledPoints,
    actual: withToday(actualPoints, todayPoint),
    today: [todayPoint],
    last_scheduled: latestPoint(scheduledPoints, today),
    last_actual: latestPoint(actualPoints, today)
  }
}

function remainingSeries(counter: Map<number, number>, total: number): DashboardPoint[] {
  let remaining = total
  return [...counter.entries()]
    .sort(([left], [right]) => left - right)
    .map(([timestamp, count]) => ({
      x: formatDate(new Date(timestamp)),
      y: (remaining -= count)
    }))
}

function remainingOn(counter: Map<number, number>, total: number, target: number) {
  return total - [...counter].reduce((sum, [date, count]) => sum + (date <= target ? count : 0), 0)
}

function withToday(points: DashboardPoint[], today: DashboardPoint) {
  return [...points.filter((point) => point.x !== today.x), today].sort(
    (left, right) => parseDate(left.x)!.getTime() - parseDate(right.x)!.getTime()
  )
}

function latestPoint(points: DashboardPoint[], today: Date) {
  return points.filter((point) => parseDate(point.x)! <= today).at(-1) || null
}

function parseDate(value: unknown): Date | null {
  if (typeof value !== 'string') return null
  const eu = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value.trim())
  const iso = /^(\d{4})[-/](\d{2})[-/](\d{2})$/.exec(value.trim())
  const parts = eu ? [eu[3], eu[2], eu[1]] : iso ? [iso[1], iso[2], iso[3]] : null
  if (!parts) return null
  const year = Number(parts[0])
  const month = Number(parts[1])
  const day = Number(parts[2])
  const date = new Date(year, month - 1, day)
  const valid =
    date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day
  return valid ? startOfDay(date) : null
}

function startOfDay(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate())
}

function dayDifference(left: Date, right: Date) {
  return Math.floor((utcDay(left) - utcDay(right)) / 86_400_000)
}

function utcDay(value: Date) {
  return Date.UTC(value.getFullYear(), value.getMonth(), value.getDate())
}

function formatDate(value: Date) {
  const day = String(value.getDate()).padStart(2, '0')
  const month = String(value.getMonth() + 1).padStart(2, '0')
  return `${day}.${month}.${value.getFullYear()}`
}
