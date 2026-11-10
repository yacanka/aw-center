import { apiClient } from '@/shared/api/http'

export interface PdfSplitParameters {
  parts: number | null
  pages_per_parts: number | null
}

/** Split one validated PDF and return the generated archive. */
export async function splitPdfArchive(file: File, parameters: PdfSplitParameters): Promise<Blob> {
  const payload = new FormData()
  payload.append('file', file)
  payload.append('parameters', JSON.stringify(parameters))
  return (
    await apiClient.post<Blob>('tools/pdf/split_pdf_zip/', payload, {
      responseType: 'blob'
    })
  ).data
}
