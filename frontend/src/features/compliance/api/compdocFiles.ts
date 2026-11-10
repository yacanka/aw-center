import { apiClient } from '@/shared/api/http'
import { compdocCollectionPath } from '@/shared/api/apiPaths'

/** Export the complete current compliance-document register for one project. */
export async function exportCompdocWorkbook(project: string): Promise<Blob> {
  return (
    await apiClient.get<Blob>(`${compdocCollectionPath(project)}export/`, {
      responseType: 'blob'
    })
  ).data
}
