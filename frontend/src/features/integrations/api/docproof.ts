import { apiClient } from '@/shared/api/http'
import { API_PATHS } from '@/shared/api/apiPaths'

/** Return the current DocProof issue for one document identifier. */
export async function searchDocproof(documentNumber: string): Promise<number> {
  const response = await apiClient.get<number>(`${API_PATHS.docproof}/search/`, {
    params: { document_no: documentNumber }
  })
  return response.data
}
