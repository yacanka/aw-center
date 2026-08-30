import { apiClient } from '@/shared/api/http'
import { API_PATHS } from '@/shared/api/apiPaths'
import type { IMsg } from '@/features/tools/models/outlook'

/** Parse one validated Outlook message without retaining route state globally. */
export async function parseOutlookMessage(message: FormData): Promise<IMsg> {
  const response = await apiClient.post<IMsg>(`${API_PATHS.outlook}/msg/parse/`, message)
  return response.data
}
