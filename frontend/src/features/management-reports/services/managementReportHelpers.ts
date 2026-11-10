import type { ManagementReport, ReportListItem } from '../models/managementReports'

/** Validate against server-authorized options, then produce a stable report scope. */
export function normalizeReportScope(selected: string[], authorized: string[]): string[] {
  if (!selected.length) throw new Error('Select at least one project.')
  if (selected.some((slug) => !authorized.includes(slug))) {
    throw new Error('Select only authorized projects.')
  }
  return [...new Set(selected)].sort()
}

export function formatReportDelta(value: number | null, percentage = false): string {
  if (value === null) return '—'
  return `${value > 0 ? '+' : ''}${value}${percentage ? ' pp' : ''}`
}

/** Client-side selection aid; the server remains authoritative for compatibility and access. */
export function compatibleBaselines(
  reports: ReportListItem[],
  current: Pick<ManagementReport, 'id' | 'captured_at' | 'schema_version' | 'project_slugs'>
): ReportListItem[] {
  const scope = [...current.project_slugs].sort().join(',')
  return reports.filter(
    (report) =>
      report.id !== current.id &&
      report.schema_version === current.schema_version &&
      [...report.project_slugs].sort().join(',') === scope &&
      Date.parse(report.captured_at) < Date.parse(current.captured_at)
  )
}

/** A shared generation gate prevents stale responses from changing the selected report. */
export function createReportRequestGuard() {
  let controller: AbortController | null = null
  let generation = 0
  function cancel() {
    generation += 1
    controller?.abort()
  }
  return {
    cancel,
    begin() {
      cancel()
      controller = new AbortController()
      const active = generation
      return { signal: controller.signal, isCurrent: () => active === generation }
    }
  }
}
