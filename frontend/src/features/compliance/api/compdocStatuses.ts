import { apiClient } from '@/shared/api/http'
import { compdocCollectionPath } from '@/shared/api/apiPaths'
import type { CompdocOption } from './compdocCatalog'

export interface CompdocStatus extends CompdocOption {
  id: string
  usage_count: number
  can_delete: boolean
}

export async function fetchCompdocStatuses(project: string): Promise<CompdocStatus[]> {
  const response = await apiClient.get<CompdocStatus[]>(
    `${compdocCollectionPath(project)}statuses/`
  )
  return response.data
}

export async function createCompdocStatus(project: string, label: string): Promise<CompdocStatus> {
  const response = await apiClient.post<CompdocStatus>(
    `${compdocCollectionPath(project)}statuses/`,
    { label }
  )
  return response.data
}

export async function deleteCompdocStatus(project: string, id: string): Promise<void> {
  await apiClient.delete(`${compdocCollectionPath(project)}statuses/${encodeURIComponent(id)}/`)
}
