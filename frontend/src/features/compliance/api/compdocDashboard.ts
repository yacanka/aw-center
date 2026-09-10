import { apiClient as axios } from '@/shared/api/http'
import type {
  CompDocDashboardSummary,
  DashboardAnalytics
} from '@/features/compliance/models/compdocDashboard'
import { compdocCollectionPath } from '@/shared/api/apiPaths'

/** Fetch complete project analytics without depending on paginated table rows. */
export async function fetchCompdocDashboard(
  projectSlug: string,
  signal?: AbortSignal
): Promise<CompDocDashboardSummary> {
  const response = await axios.get<unknown>(`${compdocCollectionPath(projectSlug)}dashboard/`, {
    signal
  })
  return parseCompdocDashboard(response.data)
}

export function parseCompdocDashboard(value: unknown): CompDocDashboardSummary {
  if (
    !isRecord(value) ||
    !isText(value.project) ||
    !isCount(value.archived) ||
    !isText(value.generated_at) ||
    !Number.isFinite(Date.parse(value.generated_at)) ||
    !Array.isArray(value.panels) ||
    !value.panels.every(isPanel) ||
    !isAnalytics(value)
  ) {
    throw new Error('The compliance dashboard response is invalid.')
  }
  return {
    ...value,
    project: value.project,
    archived: value.archived,
    generated_at: value.generated_at,
    panels: value.panels
  }
}

function isAnalytics(value: unknown): value is DashboardAnalytics {
  return (
    isRecord(value) &&
    isCount(value.total) &&
    isCount(value.overdue) &&
    isCounts(value.status_counts) &&
    isCounts(value.chart_status_counts) &&
    hasValues(value.pending_days, ['authority', 'ubm', 'aw'], isCount) &&
    hasValues(value.performance, ['scheduled', 'actual', 'approved'], isMetric) &&
    isTimeline(value.timeline) &&
    isRisk(value.risk) &&
    hasValues(
      value.data_quality,
      ['issue_count', 'missing_panel', 'unknown_status', 'blank_cover_page', 'out_of_order_dates'],
      isCount
    )
  )
}

function isPanel(value: unknown): value is CompDocDashboardSummary['panels'][number] {
  return (
    isRecord(value) &&
    isText(value.id) &&
    isText(value.panel) &&
    typeof value.ata === 'string' &&
    isAnalytics(value.analytics)
  )
}

function isMetric(value: unknown) {
  return (
    hasValues(value, ['filled', 'empty', 'percentage'], isCount) &&
    (value.percentage as number) <= 100
  )
}

function isTimeline(value: unknown) {
  return (
    hasValues(
      value,
      ['scheduled', 'actual', 'today'],
      (points) => Array.isArray(points) && points.every(isPoint)
    ) &&
    [value.last_scheduled, value.last_actual].every((point) => point === null || isPoint(point))
  )
}

function isPoint(value: unknown) {
  return (
    isRecord(value) &&
    isText(value.x) &&
    /^(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})$/.test(value.x) &&
    isCount(value.y)
  )
}

function isRisk(value: unknown) {
  return (
    isRecord(value) &&
    hasValues(value.counts, ['high', 'medium', 'low', 'none'], isCount) &&
    isCount(value.at_risk_count) &&
    isCount(value.max_score) &&
    typeof value.average_score === 'number' &&
    Number.isFinite(value.average_score) &&
    value.average_score >= 0 &&
    hasValues(
      value.policy,
      [
        'version',
        'high_score',
        'medium_score',
        'long_wait_days',
        'authority_aging_days',
        'max_score',
        'priority_limit'
      ],
      isCount
    ) &&
    Array.isArray(value.priorities) &&
    value.priorities.every(isPriority)
  )
}

function isPriority(value: unknown) {
  return (
    isRecord(value) &&
    hasValues(value, ['document_id', 'name', 'panel', 'status'], isText) &&
    typeof value.ata === 'string' &&
    isCount(value.score) &&
    isCount(value.stage_age_days) &&
    ['high', 'medium', 'low'].includes(String(value.level)) &&
    Array.isArray(value.signals) &&
    value.signals.every(isSignal)
  )
}

function isSignal(value: unknown) {
  return (
    hasValues(value, ['code', 'label', 'detail'], isText) &&
    hasValues(value, ['points', 'observed', 'threshold'], isCount) &&
    ['high', 'medium', 'low'].includes(String(value.severity)) &&
    ['days', 'cycles', 'missing'].includes(String(value.unit))
  )
}

function hasValues(
  value: unknown,
  keys: string[],
  valid: (item: unknown) => boolean
): value is Record<string, unknown> {
  return isRecord(value) && keys.every((key) => valid(value[key]))
}

function isCounts(value: unknown) {
  return isRecord(value) && Object.values(value).every(isCount)
}

function isText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Object.prototype.toString.call(value) === '[object Object]'
}
