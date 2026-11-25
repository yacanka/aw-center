import { apiClient as axios } from '@/shared/api/http'
import type { CompDocDashboardSummary } from '@/features/compliance/models/compdocDashboard'
import { compdocCollectionPath } from '@/shared/api/apiPaths'

import { parseCompdocDashboard } from '../models/parseCompdocDashboard'

export { parseCompdocDashboard }

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
