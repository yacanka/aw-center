import axios from 'axios'
import type { CompDocDashboardSummary } from '@/models/compdocDashboard'

/** Fetch complete project analytics without depending on paginated table rows. */
export async function fetchCompdocDashboard(
  projectSlug: string,
  signal?: AbortSignal
): Promise<CompDocDashboardSummary> {
  const response = await axios.get<CompDocDashboardSummary>(
    `/${encodeURIComponent(projectSlug)}/compdocs/dashboard/`,
    { signal }
  )
  return response.data
}
