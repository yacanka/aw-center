import { apiClient as axios } from '@/shared/api/http'
import type { CompDocDashboardSummary } from '@/features/compliance/models/compdocDashboard'
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
  if (!isRecord(value) || !isRecord(value.status_counts)) {
    throw new Error('The compliance dashboard response is invalid.')
  }
  const statusCounts = Object.fromEntries(
    Object.entries(value.status_counts).filter(
      (entry): entry is [string, number] =>
        typeof entry[1] === 'number' && Number.isSafeInteger(entry[1]) && entry[1] >= 0
    )
  )
  if (
    typeof value.project !== 'string' ||
    !isCount(value.total) ||
    !isCount(value.archived) ||
    !isCount(value.overdue)
  ) {
    throw new Error('The compliance dashboard response is invalid.')
  }
  return {
    project: value.project,
    total: value.total,
    archived: value.archived,
    overdue: value.overdue,
    status_counts: statusCounts
  }
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Object.prototype.toString.call(value) === '[object Object]'
}
