import { isAxiosError } from 'axios'
import { compdocCollectionPath } from '@/shared/api/apiPaths'
import { apiClient } from '@/shared/api/http'
import { isApiErrorPayload } from '@/shared/api/apiError'

export async function fetchDashboardExecutable(
  project: string,
  databasePath: string
): Promise<Blob> {
  try {
    const response = await apiClient.post<Blob>(
      `${compdocCollectionPath(project)}dashboard/executable/`,
      { database_path: databasePath },
      { responseType: 'blob', timeout: 300_000 }
    )
    return response.data
  } catch (cause) {
    const blob = isAxiosError(cause) && cause.response?.data
    if (blob instanceof Blob && blob.type.startsWith('application/json') && blob.size <= 65_536) {
      const payload: unknown = await blob
        .text()
        .then((text) => JSON.parse(text))
        .catch(() => null)
      if (isApiErrorPayload(payload)) throw payload
    }
    throw cause
  }
}
